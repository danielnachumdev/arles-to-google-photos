# AGENTS.md — scripts/

Small helpers that are **not** part of the app runtime.

## Layout

| Path | Purpose |
|------|---------|
| [pr_screenshots/](pr_screenshots/AGENTS.md) | PII-safe demo seed + `agent-browser` SPA screenshots for UI PR Proof |

## Common commands

```bash
python3 scripts/pr_screenshots/seed_demo.py
scripts/pr_screenshots/screenshots.sh /tmp/arles-pr-shots --shots job-detail,validation-report
scripts/pr_screenshots/attach_to_pr.sh <PR> /tmp/arles-pr-shots/job-detail-light.png#Job\ detail
```
