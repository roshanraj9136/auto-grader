// Applied before first paint so there is no flash of the wrong theme. Light by default; remembers the user's choice.
(function () {
  try {
    var t = localStorage.getItem("ag-theme");
    if (t === "dark" || t === "light") document.documentElement.setAttribute("data-theme", t);
  } catch (e) { /* storage blocked: stay light */ }
})();
