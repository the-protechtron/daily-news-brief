import calendar
import html
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import feedparser
import requests


def load_feeds():
    feeds = json.loads(Path("feeds.json").read_text())
    if not isinstance(feeds, dict) or not feeds or any(
        not isinstance(category, str) or not isinstance(urls, list) or not all(isinstance(url, str) and url.startswith(("https://", "http://")) for url in urls)
        for category, urls in feeds.items()
    ):
        raise ValueError("feeds.json must map category names to lists of RSS URLs")
    return feeds


def fetch_news(feeds):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    news = {category: [] for category in feeds}
    for category, urls in feeds.items():
        for url in urls:
            try:
                response = requests.get(url, headers={"User-Agent": "daily-news-brief/1.0"}, timeout=15)
                response.raise_for_status()
                feed = feedparser.parse(response.content)
                if feed.bozo and not feed.entries:
                    raise ValueError(feed.bozo_exception)
                for entry in feed.entries:
                    stamp = entry.get("published_parsed") or entry.get("updated_parsed")
                    link = entry.get("link", "")
                    if not stamp or not link.startswith(("https://", "http://")):
                        continue
                    published = datetime.fromtimestamp(calendar.timegm(stamp), timezone.utc)
                    if cutoff <= published <= datetime.now(timezone.utc):
                        news[category].append({"title": entry.get("title", "Untitled"), "link": link, "published": published})
            except Exception as exc:
                print(f"Feed failed ({url}): {exc}", flush=True)
        news[category].sort(key=lambda item: item["published"], reverse=True)
        seen = set()
        unique = []
        for item in news[category]:
            if item["link"] not in seen:
                seen.add(item["link"])
                unique.append(item)
        news[category] = unique[:25]
    return news


def curate(news, key):
    for limit in (25, 15):
        candidates = {category: [{"title": item["title"], "link": item["link"]} for item in items[:limit]] for category, items in news.items()}
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                    "temperature": 0.3,
                    "max_tokens": 1500,
                    "messages": [
                        {"role": "system", "content": "Curate a daily news digest. Return only a JSON object with keys Tech, PM, Consulting. Each value is an array of the top 3-5 items available (or fewer if fewer exist). Each item has title (one-line headline), why (one sentence on why it matters), and link. Copy links exactly from the input. Never invent items or links."},
                        {"role": "user", "content": json.dumps(candidates)},
                    ],
                },
                timeout=60,
            )
            if response.status_code == 429 and limit == 25:
                print("Groq rate limited; retrying with 15 items per category", flush=True)
                continue
            response.raise_for_status()
            result = json.loads(response.json()["choices"][0]["message"]["content"])
            if set(result) != set(news):
                raise ValueError("Groq returned unexpected categories")
            for category, items in result.items():
                allowed = {item["link"] for item in candidates[category]}
                if not isinstance(items, list) or len(items) > 5 or (candidates[category] and not items):
                    raise ValueError("Groq returned an invalid item list")
                for item in items:
                    if not isinstance(item.get("title"), str) or not isinstance(item.get("why"), str) or item.get("link") not in allowed:
                        raise ValueError("Groq returned an invalid item")
            return result
        except Exception as exc:
            print(f"Groq failed; using raw headlines: {exc}", flush=True)
            return {category: items[:limit] for category, items in news.items()}
    return news


def render(news):
    parts = ["<h1>Daily Digest</h1>"]
    for category, items in news.items():
        if not items:
            continue
        parts.append(f"<h2>{html.escape(category)}</h2><ul>")
        for item in items:
            title = html.escape(item["title"]).replace("\n", "<br>")
            link = html.escape(item["link"], quote=True)
            why = html.escape(item.get("why", "")).replace("\n", "<br>")
            parts.append(f'<li><a href="{link}">{title}</a>{" — " + why if why else ""}</li>')
        parts.append("</ul>")
    return "\n".join(parts)


def main():
    key, recipient = os.getenv("RESEND_KEY"), os.getenv("MAIL_TO")
    if not key or not recipient:
        print("RESEND_KEY and MAIL_TO are required", flush=True)
        return 1
    try:
        news = fetch_news(load_feeds())
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Feed configuration failed: {exc}", flush=True)
        return 1
    if not any(news.values()):
        print("No news from the last 24 hours; skipping email", flush=True)
        return 0
    if os.getenv("LLM_API_KEY"):
        news = curate(news, os.environ["LLM_API_KEY"])
    date = datetime.now(ZoneInfo(os.getenv("DIGEST_TIMEZONE", "Asia/Kolkata"))).date()
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {key}"},
            json={"from": os.getenv("MAIL_FROM", "Daily Digest <onboarding@resend.dev>"), "to": [recipient], "subject": f"Daily Digest - {date}", "html": render(news)},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Email failed: {exc}; response: {response.text if 'response' in locals() else 'none'}", flush=True)
        return 1
    print(f"Digest sent to {recipient}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
