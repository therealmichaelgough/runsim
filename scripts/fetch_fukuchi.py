"""Stage the Fukuchi et al. 2017 running dataset (figshare article 4543435,
CC-BY) into data/raw/fukuchi2017/ — the layout runsim.data.fukuchi expects.

Downloads the .txt/.xlsx files (~430 MB total; the .c3d/.mat archives are
skipped) via the public figshare v2 API with skip-existing semantics, so
rerunning is safe and resumes an interrupted staging. No login required.

Usage: .venv\\Scripts\\python.exe scripts\\fetch_fukuchi.py [--dest DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ARTICLE = 4543435
API = f"https://api.figshare.com/v2/articles/{ARTICLE}"
DEFAULT_DEST = Path(__file__).resolve().parents[1] / "data" / "raw" / "fukuchi2017"
KEEP_SUFFIXES = (".txt", ".xlsx")
CHUNK = 1 << 20


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    dest = ap.parse_args().dest
    dest.mkdir(parents=True, exist_ok=True)

    with urllib.request.urlopen(API, timeout=60) as r:
        files = json.load(r)["files"]
    wanted = [f for f in files if f["name"].lower().endswith(KEEP_SUFFIXES)]
    total_mb = sum(f["size"] for f in wanted) / 1e6
    print(f"{len(wanted)} files to stage ({total_mb:.0f} MB); "
          f"{len(files) - len(wanted)} non-txt/xlsx files skipped", flush=True)

    failures = 0
    for i, f in enumerate(wanted, 1):
        out = dest / f["name"]
        if out.exists() and out.stat().st_size == f["size"]:
            continue
        tmp = out.with_suffix(out.suffix + ".part")
        try:
            with urllib.request.urlopen(f["download_url"], timeout=300) as r, tmp.open("wb") as w:
                while chunk := r.read(CHUNK):
                    w.write(chunk)
            if f.get("computed_md5") and md5(tmp) != f["computed_md5"]:
                raise IOError("md5 mismatch")
            tmp.replace(out)
            print(f"[{i}/{len(wanted)}] {f['name']} ({f['size'] / 1e6:.1f} MB)", flush=True)
        except Exception as exc:
            failures += 1
            print(f"[{i}/{len(wanted)}] FAILED {f['name']}: {exc}", flush=True)
            tmp.unlink(missing_ok=True)

    if failures:
        sys.exit(f"{failures} downloads failed; rerun to retry just those")
    print("fukuchi2017 staging complete", flush=True)


if __name__ == "__main__":
    main()
