#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def read_direct_url(repo_root: Path) -> tuple[str | None, str | None]:
    matches = sorted((repo_root / ".venv").glob("lib/python*/site-packages/jcal-0.1.0.dist-info/direct_url.json"))
    if not matches:
        return None, None
    data = json.loads(matches[0].read_text())
    url = data.get("url")
    commit = (data.get("vcs_info") or {}).get("commit_id")
    return url, commit


def main() -> int:
    parser = argparse.ArgumentParser(description="Create clean jcal lunisolar snapshot and fixed patch.")
    parser.add_argument("--out-dir", default="tmp/jcal_clean")
    parser.add_argument("--from-file", default=None, help="Use an existing clean lunisolar.py file path.")
    parser.add_argument("--from-installed", action="store_true", help="Use installed jcal as clean source.")
    parser.add_argument("--url", default=None, help="VCS URL for jcal source.")
    parser.add_argument("--commit", default=None, help="VCS commit for jcal source.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    out_dir = (repo_root / args.out_dir).resolve()
    patched = (repo_root / "patches/jcal_lunisolar_patched.py").resolve()
    patch_out = (repo_root / "patches/jcal-lunisolar.patch").resolve()
    clean_out = out_dir / "jcal/core/lunisolar.py"

    if not patched.exists():
        print(f"[make_clean_jcal_snapshot] ERROR: missing patched source: {patched}", file=sys.stderr)
        return 1

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.from_file:
        src = Path(args.from_file).resolve()
        if not src.exists():
            print(f"[make_clean_jcal_snapshot] ERROR: from-file not found: {src}", file=sys.stderr)
            return 1
        clean_out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, clean_out)
    elif args.from_installed:
        code = "import jcal.core.lunisolar as m; print(m.__file__)"
        target = (
            subprocess.check_output([sys.executable, "-c", code], text=True).strip()
        )
        src = Path(target).resolve()
        clean_out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, clean_out)
    else:
        url = args.url
        commit = args.commit
        if not url or not commit:
            detected_url, detected_commit = read_direct_url(repo_root)
            url = url or detected_url
            commit = commit or detected_commit
        if not url or not commit:
            print(
                "[make_clean_jcal_snapshot] ERROR: unable to determine jcal source url/commit. "
                "Use --url and --commit.",
                file=sys.stderr,
            )
            return 1

        spec = f"jcal @ git+{url}@{commit}"
        cmd = [sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(out_dir), spec]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print("[make_clean_jcal_snapshot] ERROR: failed to fetch clean jcal source.", file=sys.stderr)
            print(proc.stderr.strip() or proc.stdout.strip(), file=sys.stderr)
            print(
                "[make_clean_jcal_snapshot] hint: network is required unless --from-file is supplied.",
                file=sys.stderr,
            )
            return 1
        if not clean_out.exists():
            print(f"[make_clean_jcal_snapshot] ERROR: clean snapshot not found: {clean_out}", file=sys.stderr)
            return 1

    diff_cmd = [
        "diff",
        "-u",
        "--label",
        "a/jcal/core/lunisolar.py",
        "--label",
        "b/jcal/core/lunisolar.py",
        str(clean_out),
        str(patched),
    ]
    proc = subprocess.run(diff_cmd, capture_output=True, text=True)
    if proc.returncode not in (0, 1):
        print("[make_clean_jcal_snapshot] ERROR: failed to generate patch diff.", file=sys.stderr)
        print(proc.stderr.strip(), file=sys.stderr)
        return 1
    patch_out.write_text(proc.stdout)
    if patch_out.stat().st_size == 0:
        print("[make_clean_jcal_snapshot] ERROR: generated patch is empty.", file=sys.stderr)
        return 1

    print(f"[make_clean_jcal_snapshot] clean: {clean_out}")
    print(f"[make_clean_jcal_snapshot] patch: {patch_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
