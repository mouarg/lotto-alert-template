# lotto-alert-template

![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/license-PolyForm--Noncommercial--1.0.0-blue)

Personal WhatsApp alerts for NZ Lotto + Powerball syndicate wins. Runs entirely on GitHub Actions — no servers, no laptop dependency, no recurring costs.

After every Wed + Sat draw, a workflow checks your syndicate's lines against the official MyLotto results and sends a WhatsApp. A Sunday heartbeat sends a weekly summary so you can confirm the system is alive.

## Example output

```
🤑 LOTTO WIN! - My syndicate
Draw 9999 - Sat 1 Jan 2099

✅ Line B: Lotto Div 5 - 25.00 NZD

💵 Cash this draw: 25.00 NZD

Winning numbers
🔵 1  🟠 11  🟠 19  🟢 22  🔴 33  🔴 38
🟢 Bonus 25    🔴 Powerball 7

💰 Kitty: 150 NZD (30 NZD each, 5 ways)
🎟 + 12 bonus tickets earned
over 50 draws since 1 Jan 2099
```

For a no-win draw you get a similar message with 😢 and "No win this draw" — never silent, so a missing alert is itself a signal.

## Quickstart (one-time setup, ~15 min)

This template is designed for non-developers. You'll never edit Python.

1. **Click "Use this template" → "Create a new repository"** at the top of this page. Name it whatever you like (e.g. `my-syndicate-tracker`). Set visibility to **Private** so your kitty stays yours.

2. **Get a CallMeBot key (free WhatsApp gateway, ~2 min):**
   - Save `+34 644 51 95 23` as a contact on your phone (call it "CallMeBot")
   - Send that contact: `I allow callmebot to send me messages`
   - It replies with your personal **7-digit API key**

3. **Add two secrets to your new repo:** Settings → Secrets and variables → Actions → New repository secret. Add:
   - `CALLMEBOT_PHONE` — your WhatsApp number in international format with no `+` (e.g. `64211234567`)
   - `CALLMEBOT_APIKEY` — the 7-digit key from CallMeBot

4. **Edit `config.json`** (create it from `config.example.json`):
   ```json
   {
     "syndicate_name": "My syndicate",
     "cost_per_draw_nzd": 1.50,
     "kitty_split_ways": 3,
     "since_date": "2099-01-01",
     "lines": [
       {"label": "A", "lotto": [1, 2, 3, 4, 5, 6], "powerball": 1},
       {"label": "B", "lotto": [7, 8, 9, 10, 11, 12], "powerball": 2}
     ]
   }
   ```

5. **Enable Actions:** click the **Actions** tab in your repo, then "I understand my workflows, go ahead and enable them". The workflow will fire on the next Wed/Sat draw.

That's it. You'll get a WhatsApp after every draw.

## Architecture

| Component | Role |
|---|---|
| `check_draw.py` | Pulls the latest draw from MyLotto, scores your lines, sends WhatsApp |
| `heartbeat.py` | Sunday weekly summary with running P&L |
| `config.json` | Your syndicate's lines, cost, name, kitty split |
| `.github/workflows/lotto.yml` | Cron Wed + Sat 09:00 + 10:00 UTC (covers NZST/NZDT) |
| `.github/workflows/heartbeat.yml` | Cron Sat 20:00 UTC (Sun morning NZ) |
| `seen_draws.json` | Idempotency — workflow commits this back to prevent double-sends |
| `totals.json` | Lifetime ledger — kitty, wins, bonus tickets |
| CallMeBot | Free WhatsApp gateway (uses Meta's official Business API under the hood) |

Zero non-stdlib dependencies — pure Python 3.

## Cost

- GitHub Actions: free tier covers ~2 min/month usage; you have 2,000 min/month available on free private repos
- CallMeBot: free for personal use, no signup beyond the WhatsApp opt-in
- **Total: $0/month**

## Limitations

- **MyLotto API only retains ~12 months of draws.** Older history needs scraping ([powerball.net](https://www.powerball.net/newzealand/results) works well).
- **Strike not supported.** The game where you pick the draw order. Easy to add if you play it.
- **WhatsApp groups not supported.** Meta blocks bots from posting into group chats. Alerts go to you 1-to-1; forward to your syndicate group manually. [Telegram](https://core.telegram.org/bots) supports group posting if you need it.
- **Bonus-ticket replays not tracked.** When you win a bonus ticket, the subscription auto-plays it as random Dip lines next draw. Those lines aren't yours to score, so any small wins on them won't appear in the kitty.

## Privacy

- Your `config.json` (lines, syndicate name) lives in **your** repo. If you fork private, no one sees it.
- Your CallMeBot phone + key are stored as **encrypted GitHub Secrets** — zero-knowledge, never committed.
- `totals.json` (your kitty/wins) is committed to your repo so the workflow can update it. Keep your repo private if you care.

## License & terms of use

**Source-available, not open source.** Licensed under [PolyForm Noncommercial 1.0.0](LICENSE).

In plain English:

- ✅ **Free for personal / noncommercial use** — running it for your own lottery syndicate, hobby projects, educational use
- ✅ **Free to fork, modify, share** for the same noncommercial purposes
- ❌ **Commercial use requires written permission** from the author — including selling alerts, paid SaaS, paid syndicate management, embedding in a commercial product
- ❌ **No sub-licensing or transferring** the license to anyone else

Copyright © 2026 Akhil Argal. Contact via [github.com/mouarg](https://github.com/mouarg) for commercial licensing.

If you use this for your own syndicate, the "forked from mouarg/lotto-alert-template" attribution stays on your repo automatically — please keep it there.

## Why this exists

Built so a Lotto Powerball syndicate can stop manually checking results every Wed and Sat night. The brief: a WhatsApp the moment we win, a running kitty so we can finally see how we're tracking.
