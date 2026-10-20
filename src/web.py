"""Read posts from the public web preview of a Telegram channel (https://t.me/s/<channel>).
No Telegram account, login or secret is needed. Works only for public channels with the preview enabled."""
import time, datetime as dt, urllib.request, urllib.error
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; drm-map/1.0; reads the public preview at low rate)"


def get(url, tries=4):
    """GET with a few polite retries (429/5xx back off)."""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "bg,en;q=0.8"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(5 * (i + 1) * (3 if e.code == 429 else 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if i < tries - 1:
                time.sleep(3 * (i + 1))
                continue
            raise


def parse_page(html):
    """-> (list of {id, utc, text}, page_has_messages)"""
    soup = BeautifulSoup(html, "html.parser")
    boxes = soup.select("div.tgme_widget_message[data-post]")
    out = []
    for w in boxes:
        t = w.select_one("time[datetime]")
        if not t:
            continue
        box = w.select_one("div.tgme_widget_message_text.js-message_text") or w.select_one("div.tgme_widget_message_text")
        text = ""
        if box:
            for br in box.find_all("br"):
                br.replace_with("\n")
            text = box.get_text().strip()          # emoji and flags are kept (they are real characters in the page)
        out.append({"id": int(w["data-post"].rsplit("/", 1)[1]),
                    "utc": dt.datetime.fromisoformat(t["datetime"]), "text": text})
    return sorted(out, key=lambda m: m["id"]), bool(boxes)


def crawl(channel, start_local, tz, max_pages=60, delay=1.0, fetch=get):
    """Walk the preview from the newest post backwards until a post older than `start_local` is seen.
    All-or-nothing: raises if the page layout is not recognised or the page limit is hit, so a broken
    run can never overwrite good data files with partial results."""
    url, seen, pages = f"https://t.me/s/{channel}", {}, 0
    while True:
        items, has = parse_page(fetch(url))
        pages += 1
        if not has:
            if pages == 1:
                raise RuntimeError("No messages found on the first page: the web preview is off, the channel "
                                   "is not public, or Telegram changed the page layout.")
            return list(seen.values())                       # ran past the first post of the channel
        for m in items:
            seen[m["id"]] = m
        oldest = items[0]
        if oldest["utc"].astimezone(tz) < start_local:
            return list(seen.values())
        if pages >= max_pages:
            raise RuntimeError(f"Reached {max_pages} pages before the start date; raise MAX_PAGES or use a later FROM_DATE.")
        url = f"https://t.me/s/{channel}?before={oldest['id']}"
        time.sleep(delay)
