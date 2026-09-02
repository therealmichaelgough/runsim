"""Download the Van Hooren et al. 2024 dataset subsets from OSF (osf.io/7qbxc).

Stages the three subsets the runsim.data.vanhooren loader expects
(~1.3 GB total) into data/raw/vanhooren2024/:

    OSF "09. Time-normalized data"  ->  09_time_normalized/
    OSF "08. Tissue loading"        ->  08_tissue_loading/
    OSF "02. Scaled models"         ->  02_scaled_models/

The ~45 GB raw folders (C3D, GRF/markers, IK/ID/DO/JRA output,
non-normalized data) are deliberately NOT downloaded.

Idempotent: files already present with the right size are skipped, and
interrupted downloads resume via HTTP Range where the server allows it.

Usage:
    .venv\\Scripts\\python.exe scripts\\fetch_vanhooren.py [--root DIR]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

NODE = "7qbxc"
API_ROOT = f"https://api.osf.io/v2/nodes/{NODE}/files/osfstorage/"
FOLDERS = {
    "09. Time-normalized data": "09_time_normalized",
    "08. Tissue loading": "08_tissue_loading",
    "02. Scaled models": "02_scaled_models",
}
DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "vanhooren2024"
CHUNK = 1 << 20  # 1 MiB
RETRIES = 5


def _get_json(session: requests.Session, url: str, **params) -> dict:
    for attempt in range(RETRIES):
        try:
            r = session.get(url, params=params or None, timeout=120)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == RETRIES - 1:
                raise
            wait = 2**attempt
            print(f"  API error ({e}); retrying in {wait}s", flush=True)
            time.sleep(wait)
    raise AssertionError("unreachable")


def _list_folder(session: requests.Session, url: str) -> list[dict]:
    """All entries (files + folders) under one OSF folder-listing URL."""
    entries: list[dict] = []
    while url:
        page = _get_json(session, url, **{"page[size]": 100})
        entries.extend(page["data"])
        url = page["links"].get("next")
    return entries


def _walk_files(session: requests.Session, folder_entry: dict, rel: Path) -> list[tuple[Path, dict]]:
    """Recursively collect (relative_path, file_entry) under an OSF folder."""
    listing_url = folder_entry["relationships"]["files"]["links"]["related"]["href"]
    out: list[tuple[Path, dict]] = []
    for entry in _list_folder(session, listing_url):
        name = entry["attributes"]["name"]
        if entry["attributes"]["kind"] == "folder":
            out.extend(_walk_files(session, entry, rel / name))
        else:
            out.append((rel / name, entry))
    return out


def _download(session: requests.Session, entry: dict, dest: Path) -> str:
    """Download one OSF file entry to dest. Returns 'skipped'/'resumed'/'downloaded'."""
    size = entry["attributes"].get("size")
    if dest.exists() and size is not None and dest.stat().st_size == size:
        return "skipped"
    url = entry["links"]["download"]
    part = dest.with_suffix(dest.suffix + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(RETRIES):
        try:
            headers = {}
            mode = "wb"
            done = 0
            status = "downloaded"
            if part.exists() and part.stat().st_size > 0:
                done = part.stat().st_size
                headers["Range"] = f"bytes={done}-"
            with session.get(url, headers=headers, stream=True, timeout=300) as r:
                r.raise_for_status()
                if headers and r.status_code == 206:
                    mode = "ab"
                    status = "resumed"
                else:  # server ignored Range (200): restart from scratch
                    done = 0
                with open(part, mode) as fh:
                    for chunk in r.iter_content(CHUNK):
                        fh.write(chunk)
                        done += len(chunk)
            if size is not None and part.stat().st_size != size:
                raise IOError(f"size mismatch: got {part.stat().st_size}, want {size}")
            part.replace(dest)
            return status
        except (requests.RequestException, IOError) as e:
            if attempt == RETRIES - 1:
                raise
            wait = 2**attempt
            print(f"  download error ({e}); retrying in {wait}s", flush=True)
            time.sleep(wait)
    raise AssertionError("unreachable")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="destination dir")
    args = ap.parse_args(argv)

    session = requests.Session()
    session.headers["User-Agent"] = "runsim-fetch-vanhooren/1.0"

    print(f"Listing OSF node {NODE} ...", flush=True)
    root_entries = {e["attributes"]["name"]: e for e in _list_folder(session, API_ROOT)}
    missing = [n for n in FOLDERS if n not in root_entries]
    if missing:
        print(f"ERROR: OSF folders not found: {missing}", file=sys.stderr)
        return 1

    plan: list[tuple[Path, dict]] = []
    for osf_name, local_name in FOLDERS.items():
        files = _walk_files(session, root_entries[osf_name], Path(local_name))
        total_mb = sum(f["attributes"].get("size") or 0 for _, f in files) / 1e6
        print(f"  {osf_name!r}: {len(files)} files, {total_mb:,.0f} MB -> {local_name}/", flush=True)
        plan.extend(files)

    total = len(plan)
    total_bytes = sum(f["attributes"].get("size") or 0 for _, f in plan)
    print(f"Total: {total} files, {total_bytes/1e9:.2f} GB -> {args.root}", flush=True)

    counts = {"skipped": 0, "resumed": 0, "downloaded": 0}
    done_bytes = 0
    t0 = time.time()
    for i, (rel, entry) in enumerate(plan, 1):
        size = entry["attributes"].get("size") or 0
        status = _download(session, entry, args.root / rel)
        counts[status] += 1
        done_bytes += size
        if status != "skipped" or i % 50 == 0 or i == total:
            rate = done_bytes / 1e6 / max(time.time() - t0, 1e-9)
            print(
                f"[{i}/{total}] {status:10s} {rel}  ({size/1e6:.1f} MB; "
                f"{done_bytes/1e9:.2f}/{total_bytes/1e9:.2f} GB, {rate:.1f} MB/s cum)",
                flush=True,
            )
    print(f"Done in {(time.time()-t0)/60:.1f} min: {counts}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
