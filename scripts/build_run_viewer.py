"""Assemble the interactive run viewer: inject viewer_gaits.json (from
export_viewer_gaits.py) into run_viewer_template.html at the
/*__GAIT_DATA__*/null marker. Output: docs/run_viewer.html."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "docs" / "run_viewer.html"

MARKERS = {
    "/*__GAIT_DATA__*/null": "viewer_gaits.json",
    "/*__ARM_DATA__*/null": "viewer_arms.json",  # optional; null when absent
}


def main() -> None:
    template = (HERE / "run_viewer_template.html").read_text(encoding="utf-8")
    for marker, fname in MARKERS.items():
        if marker not in template:
            raise SystemExit(f"marker {marker} not found in template")
        src = HERE / fname
        if src.exists():
            template = template.replace(marker, src.read_text(encoding="utf-8"))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(template, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
