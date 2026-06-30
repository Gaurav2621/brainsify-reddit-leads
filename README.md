# Reddit Lead Bot ⚡

Live-watches Reddit for people who need a **website, AI automation, or custom CRM**,
uses a free AI to score each lead and **draft a reply**, then pings you on **Telegram
with one-tap buttons**: `💬 Comment` · `✉️ DM author` · `🗑 Skip`. Tap once → it posts
from your account in seconds.

> **Why one-tap instead of full auto-post?** Reddit shadowbans/bans accounts that
> auto-post promo within ~a day, and the best subs (r/forhire, r/freelance) forbid it.
> One-tap keeps you **as fast as any competitor** (~10–20s) while a real human (you)
> approves each send — so your account survives.

## How it works

```
New Reddit post (live)  →  keyword filter  →  Gemini scores + drafts  →  Telegram + buttons
                                                                            └─ you tap → posts
```

Two modes are included:

| Mode | File | Speed | Hosting | Best for |
|---|---|---|---|---|
| **⚡ Instant (recommended)** | `bot/watch.py` | seconds | always-on (your Mac or ~$5/mo VPS) | beating competitors to fresh posts |
| 🆓 Digest (fallback) | `scraper/main.py` | ~10 min | free GitHub Actions | passive, zero-cost monitoring |

---

## Setup (~10 min)

### 1. Get the API keys (all free)

| Service | Where | What you need |
|---|---|---|
| **Reddit** | reddit.com/prefs/apps → "create app" → type **script** | client id + secret + **your username & password** (needed to post) |
| **Gemini** | aistudio.google.com/apikey | one API key |
| **Telegram** | message **@BotFather** → `/newbot` (token); message **@userinfobot** (chat id) | bot token + chat id |

> ⚠️ **Reddit 2FA:** if on, set `REDDIT_PASSWORD` to `yourpassword:123456` (password +
> current 6-digit code), or turn 2FA off for this account.
> ⚠️ **Telegram:** open your new bot and press **Start** once, or it can't message you.

### 2. Fill in YOUR details
Edit [`profile/context.md`](profile/context.md) — already pre-filled for Brainsify;
just add your Reddit username, real contact link, and pricing.

### 3. Tune coverage (optional)
Edit [`config.yaml`](config.yaml) — 36 subreddits + 61 keywords by default. Too many
alerts? Raise `min_score` (e.g. 70). Too few? Lower it / add keywords.

### 4. Test locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # paste your keys
python -m bot.watch         # streams live; post a test in a watched sub to see an alert
```
You'll get a Telegram message with buttons. Tap `💬 Comment` → check Reddit → it's posted.

---

## Keeping it running 24/7

The instant mode must stay alive. Pick one:

**A — Your Mac (free, simplest):** keep it running in the background:
```bash
nohup python -m bot.watch > bot.log 2>&1 &     # survives closing the terminal
```
(Stops when the Mac sleeps/reboots — fine for daytime hustling.)

**B — A ~$5/mo VPS (always-on, recommended for serious use):**
On any Ubuntu box, run it under `pm2` (auto-restarts, starts on boot):
```bash
npm i -g pm2
pm2 start "python -m bot.watch" --name reddit-leads
pm2 save && pm2 startup
```

**C — Free passive fallback:** if you don't want an always-on host, use the digest mode
instead — push to GitHub, add the keys as Action Secrets, and the included
[`scraper.yml`](.github/workflows/scraper.yml) workflow scans every ~10 min for free.
(No one-tap buttons in this mode — it just alerts.)

---

## Files

| File | What it does |
|---|---|
| `config.yaml` | Subreddits, keywords, thresholds (edit this) |
| `profile/context.md` | Your details for AI scoring + drafts (edit this) |
| `bot/watch.py` | ⚡ Always-on live watcher + button handler |
| `bot/reddit_actions.py` | Authenticated client — posts comments / DMs |
| `bot/telegram_bot.py` | Sends alerts with buttons, polls for taps |
| `ai/pipeline.py` | Scores each lead + writes the draft reply |
| `scraper/main.py` | 🆓 Digest mode for free GitHub Actions |

## Safety notes

- You approve every send — no message goes out without your tap.
- Vary your drafts a little and don't blast 50 comments/hour; even human-approved,
  Reddit dislikes repetitive promo. Quality > volume.
- Respect each sub's rules (some want a PM, not a comment — use `✉️ DM author` there).
