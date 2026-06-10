# Agent Task Board

Status values:

- `todo`
- `in_progress`
- `done`
- `blocked`

## Current Tasks

| ID | Status | Owner | Task |
| --- | --- | --- | --- |
| A01 | done | Codex | Create fresh package, CLI, CSV pipeline, metrics, and tests. |
| A02 | todo | unassigned | Add official-dataset schema adapter once starter kit arrives. |
| A03 | todo | unassigned | Add Streamlit or NiceGUI demo for upload, preview, audit, and download. |
| A04 | todo | unassigned | Improve target-group handling with a safe preserve/generalize policy. |
| A05 | todo | unassigned | Add stronger local utility proxy using a small open classifier if allowed. |
| A06 | todo | unassigned | Add score log template for official leaderboard submissions. |
| A07 | done | Codex | Add packaging/install instructions for judges. |
| A08 | todo | unassigned | Add final pitch outline and demo script. |

## Next Recommended Task

Build A03: a minimal UI that calls the existing `privhsd` functions. The UI
should not reimplement the pipeline.

Expected UI controls:

- CSV upload
- text column selector
- ID column selector
- mode selector
- target generalization toggle
- preview table
- audit summary
- download privatized CSV
