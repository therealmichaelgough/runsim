"""Assemble the interactive run viewer: inject viewer_gaits.json (from
export_viewer_gaits.py) into run_viewer_template.html at the
/*__GAIT_DATA__*/null marker. Output: docs/run_viewer.html."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "docs" / "run_viewer.html"

MARKER = "/*__GAIT_DATA__*/null"


def main() -> None:
    template = (HERE / "run_viewer_template.html").read_text(encoding="utf-8")
    data = (HERE / "viewer_gaits.json").read_text(encoding="utf-8")
    if MARKER not in template:
        raise SystemExit("marker not found in template")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(template.replace(MARKER, data), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
