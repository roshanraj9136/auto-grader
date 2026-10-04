"""Cancellable, time-bounded subprocess execution that never blocks the event loop.

Subprocesses run in a worker thread (works on every Windows/Linux event loop, unlike
asyncio.create_subprocess_exec under SelectorEventLoop). Cancelling the awaiting task
kills the whole process tree, which is what makes the speculative clone cheap to abort.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False
    cancelled: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.cancelled


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()


def _tail(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[-limit:]


def run_cmd(
    args: list[str],
    *,
    cwd: str | Path | None = None,
    timeout: float = 120,
    env: dict[str, str] | None = None,
    cancel: threading.Event | None = None,
    max_output: int = 200_000,
) -> CommandResult:
    """Run `args` (never through a shell) with a timeout and cooperative cancellation."""
    start = time.perf_counter()
    proc = subprocess.Popen(
        args,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        env={**os.environ, **(env or {})},
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    timed_out = cancelled = False
    while True:
        try:
            out, err = proc.communicate(timeout=0.25)
            break
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                cancelled = True
            elif time.perf_counter() - start > timeout:
                timed_out = True
            else:
                continue
            _kill_tree(proc)
            out, err = proc.communicate()
            break
    return CommandResult(
        returncode=proc.returncode if proc.returncode is not None else -1,
        stdout=_tail(out or "", max_output),
        stderr=_tail(err or "", max_output),
        duration_s=time.perf_counter() - start,
        timed_out=timed_out,
        cancelled=cancelled,
    )


async def arun(args: list[str], **kwargs) -> CommandResult:
    """Async wrapper: runs in a thread; task cancellation kills the child process."""
    cancel = threading.Event()
    fut = asyncio.ensure_future(asyncio.to_thread(run_cmd, args, cancel=cancel, **kwargs))
    try:
        return await asyncio.shield(fut)
    except asyncio.CancelledError:
        cancel.set()
        try:
            await fut  # wait for the kill so temp dirs can be removed safely
        except Exception:
            pass
        raise
