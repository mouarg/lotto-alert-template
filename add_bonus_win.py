# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Add (or subtract) a manual adjustment to the lifetime kitty in totals.json.

Used for tracking wins from bonus-ticket replay lines that the main script
can't see (random Dip lines auto-played by MyLotto subscriptions). Run
this workflow whenever your syndicate reports a bonus-ticket win so it
gets logged against the kitty.

Usage (via the GitHub Actions workflow with an input field):
    python add_bonus_win.py <amount_nzd> [note]

Negative amounts are allowed (for corrections).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TOTALS_PATH = Path(__file__).resolve().parent / "totals.json"


def main():
    if len(sys.argv) < 2:
        print("Usage: add_bonus_win.py <amount_nzd> [note]")
        sys.exit(1)

    try:
        amount = float(sys.argv[1])
    except ValueError:
        print(f"Error: '{sys.argv[1]}' is not a valid number")
        sys.exit(1)

    note = sys.argv[2] if len(sys.argv) > 2 else ""

    if not TOTALS_PATH.exists():
        t = {"cash_won_nzd": 0.0}
    else:
        t = json.loads(TOTALS_PATH.read_text())

    prev = t.get("cash_won_nzd", 0.0)
    t["cash_won_nzd"] = round(prev + amount, 2)
    t["last_updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    TOTALS_PATH.write_text(json.dumps(t, indent=2) + "\n")

    sign = "+" if amount >= 0 else ""
    print(f"Kitty: {prev:.2f} -> {t['cash_won_nzd']:.2f} NZD  ({sign}{amount:.2f})")
    if note:
        print(f"Note: {note}")


if __name__ == "__main__":
    main()
