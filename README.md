# AccessTwin

Metric digital twins of workspaces, audited by AI agents that each represent a disability profile.
Track 1 (Accessible Workplace Twin), Future of Work Hackathon @ Stanford.

**SpaceSpec** (`accesstwin/spec.py`) is the source of truth: a measured scene graph in meters. Every accessibility
check runs on it as geometry, with a citation, so generative 3D models are only used for visuals.

```shell
uv sync
uv run accesstwin audit specs/design_a.json   # audit the first-pass robotics lab
uv run pytest -q
```

Status: the wheelchair agent covers ADA 2010 §403.5.1 route widths, §304.3 turning space, §404.2.3/404.2.9 doors,
§308 reach ranges, §902.3 work surfaces and §306.3 knee clearance.
