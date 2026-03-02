"""
Fiscal Pulse — Tracker Reset
Removes pipeline_tracker.json entries for specific states so they get re-parsed.

Usage:
    python tracker_reset.py Chhattisgarh
    python tracker_reset.py Chhattisgarh Bihar Rajasthan
"""

import json
import sys
from pathlib import Path

TRACKER_PATH = "data/pipeline_tracker.json"


def reset_states(states_to_reset):
    tracker_file = Path(TRACKER_PATH)
    if not tracker_file.exists():
        print(f"Tracker not found: {TRACKER_PATH}")
        return

    with open(tracker_file) as f:
        tracker = json.load(f)

    print(f"Tracker has {len(tracker)} entries total")

    removed = 0
    tracker_new = {}
    for k, v in tracker.items():
        if any(k.startswith(f"{state}|") for state in states_to_reset):
            print(f"  Removing: {k}")
            removed += 1
        else:
            tracker_new[k] = v

    with open(tracker_file, "w") as f:
        json.dump(tracker_new, f, indent=2)

    print(f"\nRemoved {removed} tracker entries for: {states_to_reset}")
    print(f"Remaining entries: {len(tracker_new)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tracker_reset.py <State1> [State2 ...]")
        print("Example: python tracker_reset.py Chhattisgarh")
        sys.exit(1)

    states = sys.argv[1:]
    reset_states(states)
