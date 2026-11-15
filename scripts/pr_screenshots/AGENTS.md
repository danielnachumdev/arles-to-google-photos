# AGENTS.md — scripts/pr_screenshots

PII-safe local seed + `agent-browser` SPA screenshots for **UI PR Proof**. Dummy data only (`example.com`, mini fixture titles). Never point these helpers at prod or a live operator album tree.

## Agent rule (required)

**Do not capture or attach every demo route.** Choose only the SPA surfaces this PR changes (or that prove the bugfix). Attach those selected PNGs into the **PR description** Proof section via `attach_to_pr.sh` (`gh pr edit --attach`). **Never** use `gh pr comment --attach` for Proof screenshots.

## Flow

```bash
# 1) Local stack (Compose UI :5173, API :8000)
docker compose up --build -d

# 2) Seed deterministic demo jobs (mini fixture + fabricated validate report)
python3 scripts/pr_screenshots/seed_demo.py
# → writes /tmp/arles-pr-demo/state.json (preview_job_id, validate_job_id)
# → restarts the backend once so the in-process JobStore picks up the validate seed

# 3) Capture ONLY the shots this PR needs (light + dark by default)
scripts/pr_screenshots/screenshots.sh /tmp/arles-pr-shots --shots job-detail,validation-report
# New route not in the catalog yet:
# scripts/pr_screenshots/screenshots.sh /tmp/arles-pr-shots \
#   --shots my-page --extra my-page:/my-page

# 4) Attach those files into the PR body Proof (not comments)
scripts/pr_screenshots/attach_to_pr.sh <PR_NUMBER> \
  /tmp/arles-pr-shots/job-detail-light.png#Job\ detail\ light \
  /tmp/arles-pr-shots/validation-report-light.png#Validation\ report\ light
```

## Built-in `--shots` names

`home` · `jobs` · `validate` · `settings` · `job-detail` (needs seed `preview_job_id`) · `validation-report` (needs seed `validate_job_id`) · `album` (needs seed `preview_job_id`)

Add permanent catalog entries in `screenshots.sh` when a page ships on `main`. Until then use `--extra name:/path` (or `ARLES_EXTRA_SHOTS`).

## Notes

- **Auth:** `APP_ENV=local` uses `local@localhost` — no Google identity headers required for seed HTTP calls.
- **Data:** Preview comes from `tests/fixtures/day1_mini` (title `2/8/2012 - mini fixture`). Validate report is fabricated (`https://example.com/gallery/…`) and written via JobStore inside the backend container.
- **Themes / language:** SPA keys `localStorage['colorScheme']` and `localStorage['language']`. Screenshots force `en` so Proof copy is reviewable on GitHub.
- **WSL / agent-browser:** `screenshots.sh` rewrites unwritable `XDG_RUNTIME_DIR` to `/tmp/arles-ab-runtime`.
- Prefer job-detail / validation-report shots over `/jobs` list — the local volume may still contain older non-demo runs.
