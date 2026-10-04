"""Learning platform layer: accounts, assignments, submissions, dashboards and hands-on labs.

Sits on top of the grading engine (app.jobs / app.pipeline) without changing it: the engine
grades a repo, this layer records *who* submitted it, *for which assignment*, and turns the
results into dashboards, a leaderboard and a gradebook.
"""
