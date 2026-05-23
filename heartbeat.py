"""Weekly heartbeat: confirms the system is alive and sends a P&L digest.

Runs Sunday morning NZ time. Pulls the past 7 days from the MyLotto API,
adds week-on-week stats to lifetime totals from totals.json, sends one
WhatsApp summary. If the API or CallMeBot is broken, exits non-zero so
GitHub fails the workflow and emails you - the missing heartbeat is itself
the alarm.
"""

import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from check_draw import (
    BASE, HEADERS, TOTALS_PATH, COST_PER_DRAW, BONUS_TICKET_VALUE,
    SYNDICATE_NAME, KITTY_SPLIT, SINCE_DATE,
    score_draw, log,
)

WEEK_DAYS = 7


def fetch_draw(n):
    req = urllib.request.Request(f"{BASE}/api/results/v1/results/lotto/{n}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def fetch_latest():
    req = urllib.request.Request(f"{BASE}/api/results/v1/results/lotto", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def recent_draws(days=WEEK_DAYS):
    """Walk back from latest draw, collecting draws whose date is within `days` of today."""
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    out = []
    d = fetch_latest()
    while True:
        ddate = datetime.strptime(d["lotto"]["drawDate"], "%Y-%m-%d").date()
        if ddate < cutoff:
            break
        out.append(d)
        prev_n = d["lotto"]["drawNumber"] - 1
        try:
            d = fetch_draw(prev_n)
        except Exception:
            break
        time.sleep(0.2)
    return out


def send_whatsapp(msg):
    # Delegate to check_draw.send_whatsapp which handles multi-recipient logic
    from check_draw import send_whatsapp as _send
    return _send(msg)


def main():
    try:
        draws = recent_draws()
    except Exception as e:
        log(f"HEARTBEAT ERROR: MyLotto API unreachable: {e}")
        sys.exit(1)

    week_cash = 0.0
    week_bt = 0
    week_lines = []
    for d in draws:
        hits = score_draw(d)
        for h in hits:
            week_cash += h["cash"]
            if h["bonus_ticket"]:
                week_bt += 1
            tail = "free 4 NZD ticket" if (h["bonus_ticket"] and h["cash"] <= BONUS_TICKET_VALUE + 0.01) else f"{h['cash']:.2f} NZD"
            week_lines.append(f"  - Draw {d['lotto']['drawNumber']} Line {h['line']} {h['div']}: {tail}")

    totals = {}
    if TOTALS_PATH.exists():
        try:
            totals = json.loads(TOTALS_PATH.read_text())
        except Exception:
            totals = {}

    lifetime_spent = totals.get("spent_nzd", 0.0)
    lifetime_won = totals.get("cash_won_nzd", 0.0)
    lifetime_bt = totals.get("bonus_tickets_won", 0)
    lifetime_net = lifetime_won - lifetime_spent
    lifetime_draws = totals.get("draws_checked", 0)

    week_net = (week_cash - len(draws) * COST_PER_DRAW)

    today = datetime.now(timezone.utc).strftime("%a %d %b %Y")
    since = f" since {SINCE_DATE}" if SINCE_DATE else ""
    parts = [
        f"Lotto heartbeat - {SYNDICATE_NAME} ({today})",
        f"This week: {len(draws)} draw(s) checked",
    ]
    if week_lines:
        parts.append(f"Wins: {week_cash:,.2f} NZD cash + {week_bt} bonus ticket(s)")
        parts.extend(week_lines)
    else:
        parts.append("No wins this week.")
    parts.append("")
    parts.append(f"Lifetime ({lifetime_draws} draws{since}):")
    parts.append(f"  Spent:   {lifetime_spent:,.2f} NZD")
    parts.append(f"  Won:     {lifetime_won:,.2f} NZD + {lifetime_bt} bonus tickets")
    parts.append(f"  Net:     {lifetime_net:,.2f} NZD  ({lifetime_net/max(KITTY_SPLIT,1):,.2f} each)")
    best = totals.get("best_single_win")
    if best and best.get("amount_nzd"):
        parts.append(f"  Best:    {best['amount_nzd']:.2f} NZD (Draw {best['draw']}, Line {best['line']})")
    parts.append("")
    parts.append("System healthy.")

    msg = "\n".join(parts)
    try:
        send_whatsapp(msg)
        log(f"Heartbeat sent: week={len(draws)} draws, ${week_cash:.2f} cash")
    except Exception as e:
        log(f"HEARTBEAT SEND FAILED: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
