#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCH_FILE="$ROOT_DIR/patches/jcal-lunisolar.patch"
PATCHED_SOURCE="$ROOT_DIR/patches/jcal_lunisolar_patched.py"
VERIFY_MARKER="SHINTOKI_PATCH: JCAL_LUNISOLAR_V1"

resolve_python() {
  if [ -n "${PYTHON:-}" ]; then
    echo "$PYTHON"
    return 0
  fi
  if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
    echo "$ROOT_DIR/.venv/bin/python"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  return 1
}

PYTHON_BIN="$(resolve_python || true)"
if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
  if [ -n "${PYTHON:-}" ]; then
    echo "[apply_patches] ERROR: configured PYTHON is not executable: ${PYTHON}" >&2
  else
    echo "[apply_patches] ERROR: no usable python found (PYTHON/.venv/bin/python/python3)." >&2
  fi
  exit 1
fi

resolve_target() {
  "$PYTHON_BIN" - <<'PY'
import importlib
try:
    m = importlib.import_module("jcal.core.lunisolar")
except Exception as exc:
    raise SystemExit(f"failed_import:{type(exc).__name__}:{exc}")
print(m.__file__)
PY
}

verify_applied() {
  local target="$1"
  if grep -q "$VERIFY_MARKER" "$target"; then
    return 0
  fi
  echo "[apply_patches] ERROR: patch verification failed." >&2
  echo "[apply_patches] target: $target" >&2
  echo "[apply_patches] missing marker: $VERIFY_MARKER" >&2
  return 1
}

main() {
  local target=""
  local import_out=""

  if ! import_out="$(resolve_target 2>&1)"; then
    echo "[apply_patches] ERROR: failed to locate jcal target file" >&2
    echo "[apply_patches] detail: $import_out" >&2
    if [[ "$import_out" == *"No module named 'jcal'"* ]] || [[ "$import_out" == failed_import:ModuleNotFoundError:* ]]; then
      echo "[apply_patches] hint: jcal not found. Please run: pip install -e \".[compare]\" in .venv" >&2
      echo "[apply_patches] hint: Or run: PYTHON=.venv/bin/python scripts/apply_patches.sh" >&2
    else
      echo "[apply_patches] hint: activate .venv and install compare deps (pip install -e \".[dev,compare]\")" >&2
    fi
    exit 1
  fi
  target="$import_out"

  if [ ! -f "$target" ]; then
    echo "[apply_patches] ERROR: target file does not exist: $target" >&2
    exit 1
  fi

  if [ ! -s "$PATCH_FILE" ]; then
    echo "[apply_patches] ERROR: fixed patch is missing or empty: $PATCH_FILE" >&2
    exit 1
  fi

  if patch --dry-run --forward "$target" "$PATCH_FILE" >/dev/null 2>&1; then
    patch --forward "$target" "$PATCH_FILE" >/dev/null
    verify_applied "$target"
    echo "[apply_patches] applied fixed patch: $target"
    exit 0
  fi

  if patch --dry-run --reverse "$target" "$PATCH_FILE" >/dev/null 2>&1; then
    verify_applied "$target"
    echo "[apply_patches] already applied: $target"
    exit 0
  fi

  if [ -f "$PATCHED_SOURCE" ]; then
    cp "$target" "${target}.bak"
    cp "$PATCHED_SOURCE" "$target"
    if cmp -s "$target" "$PATCHED_SOURCE"; then
      verify_applied "$target"
      echo "[apply_patches] fallback replaced target from patched snapshot: $target"
      echo "[apply_patches] backup: ${target}.bak"
      exit 0
    fi
    echo "[apply_patches] ERROR: fallback replacement failed: $target" >&2
    exit 1
  fi

  echo "[apply_patches] ERROR: fixed patch cannot be applied and no fallback source exists." >&2
  echo "[apply_patches] patch: $PATCH_FILE" >&2
  echo "[apply_patches] target: $target" >&2
  exit 1
}

main "$@"
