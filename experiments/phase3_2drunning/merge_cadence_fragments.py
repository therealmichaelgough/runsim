"""Fold cadence_fragments/*.json into cadence_sweep_log.json (dedup by
imposed frequency; sequential-sweep entries win)."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "cadence_sweep_log.json"


def main() -> None:
    log = json.loads(LOG.read_text()) if LOG.exists() else []
    done = {round(r["imposed_step_freq_hz"], 4) for r in log}
    added = 0
    for frag in sorted((HERE / "cadence_fragments").glob("f*.json")):
        r = json.loads(frag.read_text())
        if round(r["imposed_step_freq_hz"], 4) not in done:
            log.append(r)
            added += 1
    log.sort(key=lambda r: r["imposed_step_freq_hz"])
    LOG.write_text(json.dumps(log, indent=2))
    print(f"merged {added} fragments; log now has {len(log)} entries")


if __name__ == "__main__":
    main()
