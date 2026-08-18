#!/usr/bin/env python3
"""
X -> Discord watcher.

Polls one or more RSS feeds, posts anything new to a Discord webhook,
and remembers what it has already sent in seen.json.

Feeds are served by an RSSHub container that GitHub Actions starts for the
duration of the job and then destroys. No hosting required.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------- config
STATE_FILE = Path(__file__).parent / "seen.json"
FEEDS_FILE = Path(__file__).parent / "feeds.json"
WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "").strip()

MAX_POST_PER_RUN = 8        # avoid dumping 20 items after downtime
SEEN_CAP = 800              # keep the state file from growing forever
TIMEOUT = 25


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def fetch(url):
    """Fetch a URL with a normal-looking user agent."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; feed-watcher/1.0)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def strip_html(s):
    """Crude tag stripper - good enough for tweet text."""
    out, depth = [], 0
    for ch in s:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    txt = "".join(out)
    for a, b in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " "),
                 ("&mdash;", "-"), ("&ndash;", "-"), ("&hellip;", "...")]:
        txt = txt.replace(a, b)
    # rss.app appends "- @handle <date>" to the tweet body; drop it
    for marker in (" - @", "- @"):
        if marker in txt:
            txt = txt.split(marker)[0]
            break
    return " ".join(txt.split())


def parse_feed(raw):
    """Return a list of dicts from an RSS 2.0 body."""
    items = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        log(f"  XML parse failed: {e}")
        return items

    # RSS 2.0
    for node in root.iter("item"):
        def get(tag):
            el = node.find(tag)
            return el.text if el is not None and el.text else ""
        guid = get("guid") or get("link")
        if not guid:
            continue
        items.append({
            "id": guid,
            "title": strip_html(get("title")),
            "link": get("link"),
            "desc": strip_html(get("description"))[:1500],
            "date": get("pubDate"),
        })

    # Atom fallback
    if not items:
        ns = "{http://www.w3.org/2005/Atom}"
        for node in root.iter(f"{ns}entry"):
            idel = node.find(f"{ns}id")
            titel = node.find(f"{ns}title")
            linkel = node.find(f"{ns}link")
            if idel is None:
                continue
            items.append({
                "id": idel.text,
                "title": strip_html(titel.text if titel is not None else ""),
                "link": linkel.get("href") if linkel is not None else "",
                "desc": "",
                "date": "",
            })
    return items


def post_discord(item, label):
    """Send one item to Discord as an embed."""
    body = item["desc"] or item["title"]
    if len(body) > 1800:
        body = body[:1797] + "..."

    payload = {
        "username": "ICT Watch",
        "embeds": [{
            "title": (item["title"] or "New post")[:250],
            "description": body,
            "url": item["link"],
            "color": 0x1DA1F2,
            "footer": {"text": label},
        }],
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        WEBHOOK, data=data,
        headers={
            "Content-Type": "application/json",
            # Cloudflare fronts discord.com and rejects the default python
            # urllib agent with 403 / error code 1010. A normal UA fixes it.
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status in (200, 204)
    except urllib.error.HTTPError as e:
        # 429 = rate limited; back off and retry once
        if e.code == 429:
            try:
                wait = json.loads(e.read()).get("retry_after", 2)
            except Exception:
                wait = 2
            log(f"  rate limited, waiting {wait}s")
            time.sleep(float(wait) + 0.5)
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    return r.status in (200, 204)
            except Exception as e2:
                log(f"  retry failed: {e2}")
                return False
        log(f"  discord error {e.code}: {e.read()[:200]}")
        return False
    except Exception as e:
        log(f"  discord error: {e}")
        return False


def main():
    if not WEBHOOK:
        log("ERROR: DISCORD_WEBHOOK not set")
        sys.exit(1)

    feeds = json.loads(FEEDS_FILE.read_text())
    seen = set()
    first_run = not STATE_FILE.exists()
    if not first_run:
        try:
            seen = set(json.loads(STATE_FILE.read_text()))
        except Exception:
            first_run = True

    if first_run:
        log("FIRST RUN - recording current items without posting")

    new_ids, sent = [], 0

    for feed in feeds:
        label, url = feed["label"], feed["url"]
        log(f"checking: {label}")
        try:
            raw = fetch(url)
        except Exception as e:
            log(f"  fetch failed: {e}")
            continue

        items = parse_feed(raw)
        log(f"  {len(items)} items in feed")

        fresh = [i for i in items if i["id"] not in seen]
        log(f"  {len(fresh)} new")

        # oldest first so Discord reads chronologically
        for item in reversed(fresh):
            if first_run:
                new_ids.append(item["id"])
                continue
            if sent >= MAX_POST_PER_RUN:
                log("  hit per-run cap, remainder left for next poll")
                break
            if post_discord(item, label):
                new_ids.append(item["id"])     # only mark seen once delivered
                sent += 1
                log(f"  posted: {item['title'][:60]}")
                time.sleep(1.0)
            else:
                log(f"  NOT marked seen, will retry: {item['title'][:50]}")

    # persist state
    combined = list(seen) + new_ids
    if len(combined) > SEEN_CAP:
        combined = combined[-SEEN_CAP:]
    STATE_FILE.write_text(json.dumps(combined, indent=0))

    log(f"done - {sent} posted, {len(combined)} ids tracked")


if __name__ == "__main__":
    main()
