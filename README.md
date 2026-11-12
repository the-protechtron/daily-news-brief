# Daily News Brief

A small, open-source Python cron job that collects RSS headlines, optionally curates them with Groq, and sends one email through Resend. It has no database, dashboard, or web server.

## What it does

1. Reads the RSS sources in `feeds.json`.
2. Keeps articles published during the last 24 hours.
3. Uses Groq to select and explain the top stories when `LLM_API_KEY` is set.
4. Falls back to raw linked headlines if Groq is unavailable or not configured.
5. Sends the HTML digest with Resend.

## Quick start

```bash
git clone https://github.com/YOUR_USERNAME/daily-news-brief.git
cd daily-news-brief
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
set -a; source .env; set +a
```

Replace the example values in `.env`, then run:

```bash
python digest.py
```

`LLM_API_KEY` is optional. Without it, the digest sends raw headlines. With Resend's `onboarding@resend.dev` sender, email can only be sent to the address used to create your Resend account.

## Customize feeds

Edit `feeds.json`. Its keys become email sections and each value is a list of RSS URLs:

```json
{
  "AI": ["https://example.com/feed.xml"],
  "Product": ["https://example.org/rss"]
}
```

Use valid `http://` or `https://` RSS URLs. A bad feed is logged and skipped; an invalid `feeds.json` stops the run before an email is sent.

## Configuration

| Variable | Required | Purpose |
| --- | --- | --- |
| `RESEND_KEY` | Yes | Resend API key |
| `MAIL_TO` | Yes | Digest recipient |
| `LLM_API_KEY` | No | Groq API key for curation |
| `GROQ_MODEL` | No | Groq model; defaults to `openai/gpt-oss-120b` |
| `MAIL_FROM` | No | Resend sender; defaults to `Daily Digest <onboarding@resend.dev>` |
| `DIGEST_TIMEZONE` | No | Date shown in the subject; defaults to `Asia/Kolkata` |

## Deploy to Render

1. Push the repository to GitHub.
2. In Render, create a **Cron Job** and connect the repository.
3. Set build command to `pip install -r requirements.txt`.
4. Set start command to `python digest.py`.
5. Add `RESEND_KEY`, `MAIL_TO`, and optionally the Groq and sender variables.
6. Set schedule to `30 1 * * *` for 7:00 AM IST (Render schedules use UTC).
7. Use **Trigger Run** once and inspect the logs.

An email failure exits non-zero so Render marks the run as failed. Feed and Groq failures do not prevent the fallback digest from sending.

## License

[MIT](LICENSE)
