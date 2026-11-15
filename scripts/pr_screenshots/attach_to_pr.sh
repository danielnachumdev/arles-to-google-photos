#!/usr/bin/env bash
# Attach selected PNG screenshots into a PR **description** (Proof), not comments.
#
# Usage:
#   scripts/pr_screenshots/attach_to_pr.sh PR_NUMBER IMAGE [IMAGE ...]
#   IMAGE may be path or 'path#Alt text'
#
# Example (only the surfaces this PR changed):
#   scripts/pr_screenshots/attach_to_pr.sh 80 \
#     /tmp/arles-pr-shots/progress-light.png#Progress\ light \
#     /tmp/arles-pr-shots/progress-dark.png#Progress\ dark
#
# Uses: gh pr edit N --body-file ... --attach file#alt
# Relative ![alt](./file.png) refs in the body are rewritten to user-attachments URLs.
#
# Agents: pass only the screenshots needed for this PR — never every PNG in a folder.
set -euo pipefail

PR=${1:?usage: attach_to_pr.sh PR_NUMBER IMAGE [IMAGE ...]}
shift
if [[ $# -eq 0 ]]; then
  echo "usage: attach_to_pr.sh PR_NUMBER IMAGE [IMAGE ...]" >&2
  echo "Pass explicit files (path or path#Alt). Do not attach every demo shot." >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI required" >&2
  exit 1
fi

STAGING=$(mktemp -d)
trap 'rm -rf "$STAGING"' EXIT

ATTACH_ARGS=()
IMAGES_FILE="$STAGING/images.txt"
: >"$IMAGES_FILE"

for spec in "$@"; do
  path=${spec%%#*}
  alt=${spec#*#}
  if [[ "$alt" == "$spec" ]]; then
    alt=$(basename "$path")
    alt=${alt%.png}
  fi
  if [[ ! -f "$path" ]]; then
    echo "missing file: $path" >&2
    exit 1
  fi
  base=$(basename "$path")
  cp -f "$path" "$STAGING/$base"
  ATTACH_ARGS+=(--attach "$STAGING/$base#$alt")
  printf '%s\t%s\n' "$alt" "$base" >>"$IMAGES_FILE"
done

BODY_FILE="$STAGING/pr-body.md"
EXISTING=$(gh pr view "$PR" --json body --jq '.body // ""')
EXISTING_FILE="$STAGING/existing.md"
printf '%s' "$EXISTING" >"$EXISTING_FILE"

python3 - "$BODY_FILE" "$EXISTING_FILE" "$IMAGES_FILE" <<'PY'
import sys
from pathlib import Path

out = Path(sys.argv[1])
existing = Path(sys.argv[2]).read_text(encoding="utf-8")
rows = Path(sys.argv[3]).read_text(encoding="utf-8").splitlines()
images = [f"![{alt}](./{base})" for alt, base in (line.split("\t", 1) for line in rows if line.strip())]
proof_images = "\n".join(images) + "\n"


def is_image_line(stripped: str) -> bool:
    if stripped.startswith("!["):
        return True
    if "user-attachments" in stripped and (
        stripped.startswith("http") or stripped.startswith("![")
    ):
        return True
    return False


if not existing.strip():
    body = (
        "## Problem\n(see commits)\n\n## Proof\n"
        + proof_images
        + "\n## Fix\n(see commits)\n\n## Verified\n(see commits)\n"
    )
elif "## Proof" in existing:
    lines = existing.splitlines(keepends=True)
    start = None
    end = len(lines)
    for i, line in enumerate(lines):
        if line.startswith("## Proof"):
            start = i
            continue
        if start is not None and i > start and line.startswith("## "):
            end = i
            break
    if start is None:
        body = existing.rstrip() + "\n\n## Proof\n" + proof_images
    else:
        section = lines[start + 1 : end]
        lead: list[str] = []
        for line in section:
            stripped = line.strip()
            if is_image_line(stripped):
                continue
            lead.append(line)
        while lead and lead[-1].strip() == "":
            lead.pop()
        new_section = ["## Proof\n"]
        if lead:
            new_section.extend(lead)
            if not str(new_section[-1]).endswith("\n"):
                new_section[-1] = str(new_section[-1]) + "\n"
            new_section.append("\n")
        new_section.append(proof_images)
        body = "".join(lines[:start] + new_section + lines[end:])
elif "\n## Fix" in existing:
    body = existing.replace("\n## Fix", "\n## Proof\n" + proof_images + "\n## Fix", 1)
else:
    body = existing.rstrip() + "\n\n## Proof\n" + proof_images

out.write_text(body, encoding="utf-8")
PY

echo "Updating PR #$PR description with $(wc -l <"$IMAGES_FILE") screenshot(s) via gh pr edit --attach"
gh pr edit "$PR" --body-file "$BODY_FILE" "${ATTACH_ARGS[@]}"

echo "Done. Screenshots are in the PR body Proof section (user-attachments URLs)."
