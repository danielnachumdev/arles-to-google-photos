#!/usr/bin/env bash
# Stamp semver into backend + frontend packaging and build a backend wheel.
#
# Usage: build_release_wheel.sh <vX.Y.Z> [out-dir]
#
# Monorepo: publishable package lives under services/backend (import root ``src``).
# Frontend package.json / src/version.ts stay aligned for SPA fallbacks.
set -euo pipefail

TAG="${1:?usage: build_release_wheel.sh <vX.Y.Z> [out-dir]}"
OUT_DIR_INPUT="${2:-dist}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="${ROOT}/services/backend"
FRONTEND_DIR="${ROOT}/services/frontend"
VERSION="${TAG#v}"

if [[ "${OUT_DIR_INPUT}" = /* ]]; then
  OUT_DIR="${OUT_DIR_INPUT}"
else
  OUT_DIR="${ROOT}/${OUT_DIR_INPUT}"
fi

if [[ ! "${VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "build_release_wheel.sh: expected tag vX.Y.Z, got ${TAG}" >&2
  exit 1
fi

python3 - "${VERSION}" "${BACKEND_DIR}" "${FRONTEND_DIR}" <<'PY'
import pathlib
import re
import sys

version = sys.argv[1]
backend = pathlib.Path(sys.argv[2])
frontend = pathlib.Path(sys.argv[3])


def replace_once(path: pathlib.Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    new, count = re.subn(pattern, replacement, text, count=1, flags=re.M)
    if count != 1:
        raise SystemExit(f"{path}: failed to update version ({count} matches for {pattern!r})")
    path.write_text(new, encoding="utf-8")


replace_once(backend / "pyproject.toml", r'^version = "[^"]+"', f'version = "{version}"')
replace_once(
    backend / "src" / "version.py",
    r'^__version__ = "[^"]+"',
    f'__version__ = "{version}"',
)
replace_once(
    frontend / "package.json",
    r'^  "version": "[^"]+"',
    f'  "version": "{version}"',
)
replace_once(
    frontend / "src" / "version.ts",
    r"^export const PACKAGE_VERSION = '[^']+'",
    f"export const PACKAGE_VERSION = '{version}'",
)
print(f"stamped backend+frontend → {version}")
PY

ROOT_PYPROJECT="${ROOT}/pyproject.toml"
if [[ -f "${ROOT_PYPROJECT}" ]]; then
  python3 - "${ROOT_PYPROJECT}" "${VERSION}" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
version = sys.argv[2]
text = path.read_text(encoding="utf-8")
new, count = re.subn(r'^version = "[^"]+"', f'version = "{version}"', text, count=1, flags=re.M)
if count != 1:
    raise SystemExit(f"{path}: failed to update version ({count} matches)")
path.write_text(new, encoding="utf-8")
print(f"stamped root pyproject → {version}")
PY
fi

cd "${BACKEND_DIR}"
mkdir -p "${OUT_DIR}"
# uv build names from pyproject name (hyphens → underscores in the wheel filename).
rm -f "${OUT_DIR}"/arles_migrator_backend-"${VERSION}"-*.whl

echo "Building wheel for arles-migrator-backend==${VERSION}…"
uv build --wheel --out-dir "${OUT_DIR}"

WHEEL="$(ls -1 "${OUT_DIR}"/arles_migrator_backend-"${VERSION}"-*.whl 2>/dev/null | head -1 || true)"
if [[ -z "${WHEEL}" ]]; then
  echo "build_release_wheel.sh: no wheel produced in ${OUT_DIR}" >&2
  ls -la "${OUT_DIR}" >&2 || true
  exit 1
fi
echo "wheel=${WHEEL}"
