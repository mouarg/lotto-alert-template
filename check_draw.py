"""Run after each NZ Lotto draw. Sends WhatsApp every draw (win or no-win).

Credentials: reads CALLMEBOT_PHONE and CALLMEBOT_APIKEY from environment.
State: seen_draws.json and totals.json next to this script.

Designed for GitHub Actions cron (and works locally too).
"""

import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

BASE = "https://pathway.mylotto.co.nz"
HEADERS = {"Accept": "application/json"}
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
SEEN_PATH = SCRIPT_DIR / "seen_draws.json"
TOTALS_PATH = SCRIPT_DIR / "totals.json"
DRAWS_CSV_PATH = SCRIPT_DIR / "draws.csv"
LOG_PATH = SCRIPT_DIR / "alert.log"

DRAWS_CSV_HEADER = [
    "draw", "date", "day",
    "n1", "n2", "n3", "n4", "n5", "n6",
    "bonus", "powerball",
    "hits", "cash_nzd", "bonus_tix", "lines_hit", "kitty_after",
]
BONUS_TICKET_VALUE = 4.00


def _load_config():
    """Load syndicate config from config.json next to this script."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"{CONFIG_PATH} not found. Create one with your syndicate's lines, "
            f"cost per draw, name, and kitty split. See config.example.json."
        )
    cfg = json.loads(CONFIG_PATH.read_text())
    lines = [(L["label"], set(L["lotto"]), L["powerball"]) for L in cfg["lines"]]
    return {
        "name": cfg.get("syndicate_name", "Lotto syndicate"),
        "cost_per_draw": float(cfg.get("cost_per_draw_nzd", 0)),
        "kitty_split": int(cfg.get("kitty_split_ways", 1)),
        "since_date": cfg.get("since_date", ""),
        "lines": lines,
    }


CONFIG = _load_config()
LINES = CONFIG["lines"]
COST_PER_DRAW = CONFIG["cost_per_draw"]
SYNDICATE_NAME = CONFIG["name"]
KITTY_SPLIT = CONFIG["kitty_split"]


def _human_since_date(iso_str):
    """Convert ISO date (2099-01-01) to '1 Jan 2099' so WhatsApp doesn't auto-link it."""
    if not iso_str:
        return ""
    try:
        return datetime.strptime(iso_str, "%Y-%m-%d").strftime("%d %b %Y").lstrip("0")
    except Exception:
        return iso_str


SINCE_DATE = _human_since_date(CONFIG["since_date"])


def log(msg):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def fetch_latest():
    req = urllib.request.Request(f"{BASE}/api/results/v1/results/lotto", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def lotto_division(match_count, has_bonus):
    if match_count == 6: return 1
    if match_count == 5 and has_bonus: return 2
    if match_count == 5: return 3
    if match_count == 4 and has_bonus: return 4
    if match_count == 4: return 5
    if match_count == 3 and has_bonus: return 6
    if match_count == 3: return 7
    return 0


def parse_money(s):
    if not s: return (0.0, False)
    s = str(s).strip()
    if "ROLLOVER" in s.upper(): return (0.0, False)
    if s.lower().startswith("bonus ticket"):
        if "+" in s:
            try:
                tail = s.split("+", 1)[1].strip().replace("$", "").replace(",", "")
                return (BONUS_TICKET_VALUE + float(tail), True)
            except Exception:
                return (BONUS_TICKET_VALUE, True)
        return (BONUS_TICKET_VALUE, True)
    try:
        return (float(s.replace("$", "").replace(",", "")), False)
    except Exception:
        return (0.0, False)


def score_draw(draw):
    lotto = draw.get("lotto") or {}
    pb_data = draw.get("powerBall") or {}
    if not lotto:
        return []
    winning = {int(n) for n in lotto["lottoWinningNumbers"]["numbers"]}
    bonus = int(lotto["lottoWinningNumbers"]["bonusBalls"])
    pb_num = int(pb_data["powerballWinningNumber"]) if pb_data.get("powerballWinningNumber") else None

    lotto_prize_by_div = {w["division"]: w for w in lotto.get("lottoWinners", [])}
    pb_prize_by_div = {w["division"]: w for w in pb_data.get("powerballWinners", [])}

    hits = []
    for label, nums, pb in LINES:
        mc = len(nums & winning)
        has_bonus = bonus in nums
        has_pb = (pb_num is not None and pb == pb_num)
        div = lotto_division(mc, has_bonus)
        if div == 0:
            continue
        if has_pb:
            info = pb_prize_by_div.get(div, {})
            cash, is_bt = parse_money(info.get("combinedPrizeValue", ""))
            div_label = f"PB Div {div}"
        else:
            info = lotto_prize_by_div.get(div, {})
            cash, is_bt = parse_money(info.get("prizeValue", ""))
            div_label = f"Lotto Div {div}"
        hits.append({"line": label, "div": div_label, "cash": cash,
                     "bonus_ticket": is_bt, "matched": mc,
                     "match_bonus": has_bonus, "match_pb": has_pb})
    return hits


def _human_date(date_str):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return d.strftime("%a %d %b %Y")


def _next_draw_date(draw_date_str):
    """NZ Lotto draws Wed + Sat. Given today's draw date, return the next one."""
    d = datetime.strptime(draw_date_str, "%Y-%m-%d").date()
    delta = 3 if d.weekday() == 2 else 4  # Wed (2) -> +3 to Sat; Sat (5) -> +4 to Wed
    return (d + timedelta(days=delta)).strftime("%a %d %b")


def _ball(n):
    """Emoji ball matching the MyLotto NZ official colour scheme."""
    n = int(n)
    if n < 10:   return "\U0001F535"   # blue (1-9)
    if n < 20:   return "\U0001F7E0"   # orange (10-19)
    if n < 30:   return "\U0001F7E2"   # green (20-29)
    if n < 40:   return "\U0001F534"   # red (30-39)
    return "\U0001F7E3"                # purple (40)


def _balls_block(nums, bonus, pb):
    """Render the winning numbers as coloured balls.

    Uses NBSP (\\u00A0) between ball and number so WhatsApp word-wrap doesn't
    split them. Regular spaces between groups so wrap happens at safe points.
    """
    NBSP = " "
    lotto_line = "  ".join(f"{_ball(n)}{NBSP}{int(n)}" for n in nums)
    bonus_line = f"{_ball(bonus)}{NBSP}Bonus{NBSP}{int(bonus)}"
    pb_line = f"\U0001F534{NBSP}Powerball{NBSP}{int(pb)}"
    return (f"*Winning numbers*\n"
            f"{lotto_line}\n"
            f"{bonus_line}    {pb_line}")


def _nzd(amount, decimals=0):
    """Format NZD amount without using '$<digit>' (CallMeBot eats $1, $2, etc as template vars)."""
    fmt = f"{{:,.{decimals}f}}".format(abs(amount))
    sign = "-" if amount < 0 else ""
    return f"{sign}{fmt} NZD"


def _kitty_footer():
    """Show the syndicate kitty (cash won + bonus tickets), suitable for the alert footer."""
    if not TOTALS_PATH.exists():
        return ""
    try:
        t = json.loads(TOTALS_PATH.read_text())
    except Exception:
        return ""
    won = t.get("cash_won_nzd", 0)
    bts = t.get("bonus_tickets_won", 0)
    each = won / max(KITTY_SPLIT, 1)
    n_draws = t.get("draws_checked", 0)
    lines = [f"\U0001F4B0 *Kitty: {_nzd(won)}* ({_nzd(each)} each, {KITTY_SPLIT} ways)"]
    if bts:
        lines.append(f"\U0001F39F  + {bts} bonus tickets earned")
    since_phrase = f" since {SINCE_DATE}" if SINCE_DATE else ""
    lines.append(f"_over {n_draws} draws{since_phrase}_")
    return "\n".join(lines)


def format_win_message(draw, hits):
    lotto = draw["lotto"]
    pb = draw["powerBall"]
    nums = lotto["lottoWinningNumbers"]["numbers"]
    bonus = lotto["lottoWinningNumbers"]["bonusBalls"]
    pb_num = pb.get("powerballWinningNumber", "?")

    cash_total = sum(h["cash"] for h in hits) - sum(BONUS_TICKET_VALUE for h in hits if h["bonus_ticket"])
    bt_count = sum(1 for h in hits if h["bonus_ticket"])

    hit_lines = []
    for h in hits:
        cash_only = h["cash"] - (BONUS_TICKET_VALUE if h["bonus_ticket"] else 0)
        if h["bonus_ticket"] and cash_only <= 0.01:
            tail = "free 4 NZD ticket"
        else:
            tail = f"*{_nzd(cash_only, 2)}*"
        hit_lines.append(f"✅ Line {h['line']}: {h['div']} - {tail}")

    parts = [
        f"\U0001F911 *LOTTO WIN!* - {SYNDICATE_NAME}",
        f"_Draw {lotto['drawNumber']} - {_human_date(lotto['drawDate'])}_",
        "",
        *hit_lines,
        "",
        f"\U0001F4B5 *Cash this draw: {_nzd(cash_total, 2)}*",
    ]
    if bt_count:
        parts.append(f"\U0001F39F *Bonus tickets: {bt_count}*")
    parts.extend(["", _balls_block(nums, bonus, pb_num)])
    footer = _kitty_footer()
    if footer:
        parts.extend(["", footer])
    return "\n".join(parts)


def format_nowin_message(draw):
    lotto = draw["lotto"]
    pb = draw["powerBall"]
    nums = lotto["lottoWinningNumbers"]["numbers"]
    bonus = lotto["lottoWinningNumbers"]["bonusBalls"]
    pb_num = pb.get("powerballWinningNumber", "?")

    parts = [
        f"\U0001F622 *No win this draw* - {SYNDICATE_NAME}",
        f"_Draw {lotto['drawNumber']} - {_human_date(lotto['drawDate'])}_",
        "",
        _balls_block(nums, bonus, pb_num),
        "",
        f"\U0001F39F _Next draw: {_next_draw_date(lotto['drawDate'])}_",
    ]
    footer = _kitty_footer()
    if footer:
        parts.extend(["", footer])
    return "\n".join(parts)


def _recipients():
    """Return list of (phone, apikey) tuples from env vars.

    Supports unlimited recipients via numbered suffixes:
      CALLMEBOT_PHONE   + CALLMEBOT_APIKEY     (primary)
      CALLMEBOT_PHONE_2 + CALLMEBOT_APIKEY_2   (second person)
      CALLMEBOT_PHONE_3 + CALLMEBOT_APIKEY_3   (third person)
      ...up to _9
    """
    out = []
    for suffix in [""] + [f"_{i}" for i in range(2, 10)]:
        phone = (os.environ.get(f"CALLMEBOT_PHONE{suffix}") or "").strip().lstrip("﻿")
        apikey = (os.environ.get(f"CALLMEBOT_APIKEY{suffix}") or "").strip().lstrip("﻿")
        if phone and apikey:
            out.append((phone, apikey))
    return out


def send_whatsapp(msg):
    recipients = _recipients()
    if not recipients:
        raise RuntimeError("CALLMEBOT_PHONE and CALLMEBOT_APIKEY must be set in environment")
    errors = []
    for phone, apikey in recipients:
        url = ("https://api.callmebot.com/whatsapp.php"
               f"?phone={phone}&text={urllib.parse.quote(msg)}&apikey={apikey}")
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                body = r.read().decode("utf-8", errors="replace")
                if r.status != 200 or ("Message queued" not in body and "ERROR" in body):
                    errors.append(f"recipient {phone[-4:]}: status={r.status} body={body[:200]}")
        except Exception as e:
            errors.append(f"recipient {phone[-4:]}: {e}")
    if errors:
        raise RuntimeError("CallMeBot send failures: " + " | ".join(errors))


def load_seen():
    if SEEN_PATH.exists():
        try:
            return set(json.loads(SEEN_PATH.read_text()))
        except Exception:
            return set()
    return set()


def save_seen(seen):
    SEEN_PATH.write_text(json.dumps(sorted(seen)))


def update_totals(draw, hits):
    """Append this draw's outcome to the running lifetime ledger.

    cash_won_nzd tracks REAL cash only (excludes the notional $4 bonus-ticket value
    that parse_money bundles in). Bonus tickets are counted separately.
    """
    if not TOTALS_PATH.exists():
        return
    try:
        t = json.loads(TOTALS_PATH.read_text())
    except Exception:
        return

    cash = sum(h["cash"] for h in hits) - sum(BONUS_TICKET_VALUE for h in hits if h["bonus_ticket"])
    bt = sum(1 for h in hits if h["bonus_ticket"])

    t["draws_checked"] = t.get("draws_checked", 0) + 1
    t["spent_nzd"] = round(t.get("spent_nzd", 0.0) + COST_PER_DRAW, 2)
    t["cash_won_nzd"] = round(t.get("cash_won_nzd", 0.0) + cash, 2)
    t["bonus_tickets_won"] = t.get("bonus_tickets_won", 0) + bt
    counts = t.setdefault("div_counts", {})
    for h in hits:
        counts[h["div"]] = counts.get(h["div"], 0) + 1

    best = t.get("best_single_win") or {"amount_nzd": 0}
    for h in hits:
        cash_only = h["cash"] - (BONUS_TICKET_VALUE if h["bonus_ticket"] else 0)
        if cash_only > best.get("amount_nzd", 0):
            best = {"amount_nzd": cash_only, "draw": draw["lotto"]["drawNumber"],
                    "date": draw["lotto"]["drawDate"], "line": h["line"]}
    t["best_single_win"] = best
    t["last_updated"] = datetime.now().isoformat(timespec="seconds") + "Z"

    TOTALS_PATH.write_text(json.dumps(t, indent=2))


def append_to_draws_csv(draw, hits):
    """Append a row to draws.csv for this draw. Creates file with header if missing."""
    lotto = draw["lotto"]
    pb = draw.get("powerBall", {}) or {}
    nums = sorted(int(x) for x in lotto["lottoWinningNumbers"]["numbers"])
    bonus = int(lotto["lottoWinningNumbers"]["bonusBalls"])
    pb_raw = pb.get("powerballWinningNumber")
    pb_num = int(pb_raw) if pb_raw else None

    cash = sum(h["cash"] for h in hits) - sum(BONUS_TICKET_VALUE for h in hits if h["bonus_ticket"])
    bt = sum(1 for h in hits if h["bonus_ticket"])

    # Kitty after this draw — read from totals.json (already updated by update_totals before this call)
    kitty = 0.0
    if TOTALS_PATH.exists():
        try:
            kitty = json.loads(TOTALS_PATH.read_text()).get("cash_won_nzd", 0.0)
        except Exception:
            pass

    if hits:
        parts = []
        for h in hits:
            cash_only = h["cash"] - (BONUS_TICKET_VALUE if h["bonus_ticket"] else 0)
            tag = f"{cash_only:.2f}" if cash_only > 0.01 else "BT"
            parts.append(f"{h['line']}:{h['div']}({tag})")
        lines_hit = "; ".join(parts)
    else:
        lines_hit = ""

    new_file = not DRAWS_CSV_PATH.exists()
    with open(DRAWS_CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(DRAWS_CSV_HEADER)
        w.writerow([
            lotto["drawNumber"],
            lotto["drawDate"],
            lotto.get("drawDay", ""),
            *[f"{n:02d}" for n in nums],
            f"{bonus:02d}",
            f"{pb_num:02d}" if pb_num is not None else "",
            len(hits),
            f"{cash:.2f}",
            bt,
            lines_hit,
            f"{kitty:.2f}",
        ])


def main():
    try:
        draw = fetch_latest()
    except Exception as e:
        log(f"ERROR fetching latest draw: {e}")
        sys.exit(1)

    n = draw["lotto"]["drawNumber"]
    ddate = draw["lotto"]["drawDate"]
    seen = load_seen()
    if n in seen:
        log(f"Draw #{n} ({ddate}) already processed; skipping.")
        return

    hits = score_draw(draw)
    update_totals(draw, hits)        # update totals first so message footer + CSV row both have current kitty
    append_to_draws_csv(draw, hits)  # log this draw to the per-draw CSV ledger

    msg = format_win_message(draw, hits) if hits else format_nowin_message(draw)
    try:
        send_whatsapp(msg)
        kind = f"{len(hits)} hit(s)" if hits else "no wins"
        log(f"Draw #{n} ({ddate}): {kind} - WhatsApp sent.")
    except Exception as e:
        log(f"Draw #{n} ({ddate}): SEND FAILED: {e}")
        sys.exit(2)

    seen.add(n)
    save_seen(seen)


if __name__ == "__main__":
    main()
