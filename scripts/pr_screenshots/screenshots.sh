#!/usr/bin/env bash
# Full-page SPA screenshots via agent-browser for UI PR Proof.
#
# Capture only the surfaces the current PR needs — do not dump every route.
#
# Usage:
#   scripts/pr_screenshots/screenshots.sh OUTDIR --shots job-detail,validation-report [--themes light dark]
#   ARLES_SHOTS=job-detail scripts/pr_screenshots/screenshots.sh OUTDIR
#
# Built-in shot names → paths:
#   home                 /
#   jobs                 /jobs
#   validate             /validate
#   settings             /settings
#   job-detail           /jobs/<preview_job_id>       (needs seed state)
#   validation-report    /jobs/<validate_job_id>      (needs seed state)
#   album                /albums/<preview_job_id>     (needs seed state)
#
# New pages for a feature PR (extend without editing this script permanently):
#   --extra name:/path   or  ARLES_EXTRA_SHOTS=name:/path,other:/other
#
# Env:
#   ARLES_WEB_URL            default http://127.0.0.1:5173
#   ARLES_API_URL            default http://127.0.0.1:8000
#   ARLES_DEMO_VIEWPORT      default "1440 900"
#   ARLES_DEMO_STATE         seed state JSON (default /tmp/arles-pr-demo/state.json)
#   ARLES_DEMO_PREVIEW_ID    override preview job id
#   ARLES_DEMO_VALIDATE_ID   override validate job id
#   ARLES_SHOTS              comma-separated shot names (required unless --shots)
#   ARLES_EXTRA_SHOTS        comma-separated name:/path extras
#   ARLES_THEMES             space/comma themes (default light dark)
#   ARLES_LANGUAGE           SPA language forced for shots (default en)
#   XDG_RUNTIME_DIR          default /tmp/arles-ab-runtime (WSL-friendly)
#
# Requires: agent-browser, seeded local API, Compose (or Vite) web up.
# Dummy data only — never point at prod.
set -euo pipefail

OUT=${1:?usage: screenshots.sh OUTDIR --shots job-detail[,validation-report...] [--themes light dark] [--extra name:/path]}
shift

SHOTS_CSV=${ARLES_SHOTS:-}
THEMES_RAW=${ARLES_THEMES:-light dark}
EXTRA_CSV=${ARLES_EXTRA_SHOTS:-}
LANGUAGE=${ARLES_LANGUAGE:-en}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --shots)
      SHOTS_CSV=${2:?--shots needs a comma-separated list}
      shift 2
      ;;
    --themes)
      shift
      THEMES_RAW=""
      while [[ $# -gt 0 && "$1" != --* ]]; do
        if [[ -n "$THEMES_RAW" ]]; then
          THEMES_RAW="$THEMES_RAW $1"
        else
          THEMES_RAW=$1
        fi
        shift
      done
      THEMES_RAW=${THEMES_RAW:?--themes needs a value}
      ;;
    --extra)
      if [[ -n "$EXTRA_CSV" ]]; then
        EXTRA_CSV="${EXTRA_CSV},${2:?--extra needs name:/path}"
      else
        EXTRA_CSV=${2:?--extra needs name:/path}
      fi
      shift 2
      ;;
    light|dark)
      # Back-compat: trailing theme tokens without --themes
      THEMES_RAW="$*"
      break
      ;;
    *)
      echo "unknown arg: $1" >&2
      echo "usage: screenshots.sh OUTDIR --shots job-detail,validation-report [--themes light dark] [--extra name:/path]" >&2
      exit 1
      ;;
  esac
done

SHOTS_CSV=${SHOTS_CSV// /}
if [[ -z "$SHOTS_CSV" ]]; then
  echo "No shots selected. Pass --shots name,name or set ARLES_SHOTS." >&2
  echo "Built-ins: home jobs validate settings job-detail validation-report album" >&2
  echo "Agents: choose only surfaces changed by this PR (e.g. --shots job-detail,validation-report)." >&2
  exit 1
fi

THEMES=${THEMES_RAW//,/ }
WEB=${ARLES_WEB_URL:-http://127.0.0.1:5173}
API=${ARLES_API_URL:-http://127.0.0.1:8000}
STATE=${ARLES_DEMO_STATE:-/tmp/arles-pr-demo/state.json}
VIEWPORT=${ARLES_DEMO_VIEWPORT:-1440 900}

_RUNTIME_FALLBACK=/tmp/arles-ab-runtime
if [[ -z "${XDG_RUNTIME_DIR:-}" || ! -d "${XDG_RUNTIME_DIR}" || ! -w "${XDG_RUNTIME_DIR}" ]]; then
  export XDG_RUNTIME_DIR=$_RUNTIME_FALLBACK
fi
mkdir -p "$OUT" "$XDG_RUNTIME_DIR"

if ! command -v agent-browser >/dev/null 2>&1; then
  echo "agent-browser not found; install: npm i -g agent-browser && agent-browser install" >&2
  exit 1
fi

curl -fsS "$API/api/settings" >/dev/null || {
  echo "API not reachable at $API — start: docker compose up --build -d" >&2
  exit 1
}
curl -fsS "$WEB/" >/dev/null || {
  echo "Web not reachable at $WEB — start: docker compose up --build -d" >&2
  exit 1
}

PREVIEW_ID=${ARLES_DEMO_PREVIEW_ID:-}
VALIDATE_ID=${ARLES_DEMO_VALIDATE_ID:-}
if [[ -f "$STATE" ]]; then
  if [[ -z "$PREVIEW_ID" ]]; then
    PREVIEW_ID=$(jq -r '.preview_job_id // empty' "$STATE")
  fi
  if [[ -z "$VALIDATE_ID" ]]; then
    VALIDATE_ID=$(jq -r '.validate_job_id // empty' "$STATE")
  fi
fi

declare -A BUILTIN_PATHS=(
  [home]=/
  [jobs]=/jobs
  [validate]=/validate
  [settings]=/settings
)

if [[ -n "$PREVIEW_ID" ]]; then
  BUILTIN_PATHS[job-detail]="/jobs/$PREVIEW_ID"
  BUILTIN_PATHS[album]="/albums/$PREVIEW_ID"
fi
if [[ -n "$VALIDATE_ID" ]]; then
  BUILTIN_PATHS[validation-report]="/jobs/$VALIDATE_ID"
fi

declare -A EXTRA_PATHS=()
if [[ -n "$EXTRA_CSV" ]]; then
  IFS=',' read -r -a extra_items <<<"$EXTRA_CSV"
  for item in "${extra_items[@]}"; do
    [[ -z "$item" ]] && continue
    name=${item%%:*}
    path=${item#*:}
    if [[ -z "$name" || "$name" == "$path" || -z "$path" ]]; then
      echo "invalid --extra / ARLES_EXTRA_SHOTS entry: $item (want name:/path)" >&2
      exit 1
    fi
    EXTRA_PATHS[$name]=$path
  done
fi

path_for_shot() {
  local name=$1
  if [[ -n "${EXTRA_PATHS[$name]:-}" ]]; then
    echo "${EXTRA_PATHS[$name]}"
    return 0
  fi
  if [[ -n "${BUILTIN_PATHS[$name]:-}" ]]; then
    echo "${BUILTIN_PATHS[$name]}"
    return 0
  fi
  return 1
}

IFS=',' read -r -a SHOT_NAMES <<<"$SHOTS_CSV"
ROUTES=()
for name in "${SHOT_NAMES[@]}"; do
  [[ -z "$name" ]] && continue
  if [[ "$name" == "job-detail" || "$name" == "album" ]] && [[ -z "$PREVIEW_ID" ]]; then
    echo "shot $name needs ARLES_DEMO_PREVIEW_ID or seed state preview_job_id" >&2
    exit 1
  fi
  if [[ "$name" == "validation-report" && -z "$VALIDATE_ID" ]]; then
    echo "shot validation-report needs ARLES_DEMO_VALIDATE_ID or seed state validate_job_id" >&2
    exit 1
  fi
  path=$(path_for_shot "$name") || {
    echo "unknown shot: $name" >&2
    echo "Built-ins: home jobs validate settings job-detail validation-report album" >&2
    echo "Or pass --extra name:/path" >&2
    exit 1
  }
  ROUTES+=("$name:$path")
done

SESSION=$(agent-browser session id --scope worktree --prefix arles-pr 2>/dev/null || true)
AB=(agent-browser)
if [[ -n "$SESSION" ]]; then
  AB=(agent-browser --session "$SESSION")
fi

ab() { "${AB[@]}" "$@"; }

# shellcheck disable=SC2086
ab set viewport $VIEWPORT >/dev/null

set_theme_and_lang() {
  local theme=$1
  ab eval "
    localStorage.setItem('colorScheme', '$theme');
    localStorage.setItem('language', '$LANGUAGE');
    document.documentElement.dataset.colorScheme = '$theme';
    document.documentElement.lang = '$LANGUAGE';
    window.dispatchEvent(new Event('arles-settings-changed'));
  " >/dev/null
  ab wait 600 >/dev/null
}

ab open "$WEB/" >/dev/null
ab wait 1200 >/dev/null

for theme in $THEMES; do
  set_theme_and_lang "$theme"
  for route in "${ROUTES[@]}"; do
    name=${route%%:*}
    path=${route#*:}
    ab open "$WEB$path" >/dev/null
    ab eval "
      localStorage.setItem('colorScheme', '$theme');
      localStorage.setItem('language', '$LANGUAGE');
      document.documentElement.dataset.colorScheme = '$theme';
      document.documentElement.lang = '$LANGUAGE';
    " >/dev/null
    ab wait 2200 >/dev/null
    ab screenshot --full "$OUT/$name-$theme.png" >/dev/null
    echo "wrote $OUT/$name-$theme.png"
  done
done

ls -1 "$OUT"
