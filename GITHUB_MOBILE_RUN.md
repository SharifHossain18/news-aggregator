# Run News Aggregator Without Laptop (GitHub)

This project is now configured to run in GitHub Actions, so your laptop can stay off.

## 1) Add GitHub Secrets

In your repo: **Settings -> Secrets and variables -> Actions -> New repository secret**

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## 2) Automatic Daily Run

Workflow file: `.github/workflows/scrape.yml`

- Scheduled at **7:05 AM Bangladesh time** (1:05 AM UTC)
- Runs daily digest in cloud and sends to Telegram

## 3) Manual Run From Mobile

Use GitHub mobile app or browser:

1. Open your repo
2. Go to **Actions**
3. Open **News Aggregator Cloud Run**
4. Tap **Run workflow**
5. Pick mode:
   - `digest` (full daily digest now)
   - `trigger` (alert scan now)
   - `stats` (send source stats to Telegram)
   - `search` (set `query` too)

Optional input:
- `strict_core_only`: `true` or `false`

## 4) Verify It Worked

- Check Action run logs in GitHub
- Confirm Telegram message arrives

If Telegram does not arrive, first check that both secrets are set correctly.
