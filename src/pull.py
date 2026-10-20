"""Fetch posts from the Telegram channel into data/result_DD.MM.YYYY.json (one file per day).

Each run rewrites the days from `start` up to today, so re-running is always safe (no duplicates),
a post published after the last run of the day is picked up next time, and a missed day is backfilled.
"""
import os, sys, json, datetime as dt
from zoneinfo import ZoneInfo
from common import DATA, load_all

CHANNEL = os.environ.get("TG_CHANNEL", "drmjournal")
SOURCE = os.environ.get("SOURCE", "web")       # "web" = public preview, no login (default); "api" = Telethon, needs a login
TZ = ZoneInfo(os.environ.get("TZ_NAME", "Europe/Sofia"))   # day boundaries are in this timezone


def fetch_day(client, day):
    """All text posts of one calendar day (in TZ), oldest first, in the same shape as the Desktop export."""
    start = dt.datetime.combine(day, dt.time.min, TZ)
    end = start + dt.timedelta(days=1)
    out = []
    for m in client.iter_messages(CHANNEL, offset_date=end):      # newest first, older than `end`
        t = m.date.astimezone(TZ)
        if t < start:
            break
        if m.message:
            out.append({
                "id": m.id,
                "type": "message",
                "date": t.strftime("%Y-%m-%dT%H:%M:%S"),
                "date_unixtime": str(int(m.date.timestamp())),
                "text": m.message,
            })
    return sorted(out, key=lambda x: x["id"])


def save_day(day, msgs):
    name = DATA / f"result_{day:%d.%m.%Y}.json"
    tmp = name.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"name": "De Re Militari", "messages": msgs}, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, name)          # atomic: a failed run can never leave a half-written file
    return name


def start_date(today):
    env = os.environ.get("FROM_DATE", "").strip()
    if env:
        return dt.date.fromisoformat(env)
    last = max((dt.date.fromisoformat(m["date"][:10]) for m in load_all()), default=today)
    return min(last, today - dt.timedelta(days=1))      # at least yesterday + today; more if days were missed


def pull_web(start, today, crawler=None):
    """Public web preview: no login. Writes the files only after the whole crawl succeeded."""
    from collections import defaultdict
    import web
    start_local = dt.datetime.combine(start, dt.time.min, TZ)
    msgs = (crawler or web.crawl)(CHANNEL, start_local, TZ, max_pages=int(os.environ.get("MAX_PAGES", "60")))
    by_day = defaultdict(list)
    for m in msgs:
        local = m["utc"].astimezone(TZ)
        if local.date() >= start and m["text"]:
            by_day[local.date()].append({"id": m["id"], "type": "message", "date": local.strftime("%Y-%m-%dT%H:%M:%S"),
                                         "date_unixtime": str(int(m["utc"].timestamp())), "text": m["text"]})
    day = start
    while day <= today:
        day_msgs = sorted(by_day.get(day, []), key=lambda x: x["id"])
        print(f"{day}: {len(day_msgs)} posts -> {save_day(day, day_msgs).name}")
        day += dt.timedelta(days=1)


def pull_api(start, today):
    """Telethon (optional, needs a Telegram login stored as secrets)."""
    from telethon.sync import TelegramClient
    from telethon.sessions import StringSession
    need = [k for k in ("TG_API_ID", "TG_API_HASH", "TG_SESSION") if not os.environ.get(k)]
    if need:
        sys.exit("SOURCE=api needs: " + ", ".join(need))
    with TelegramClient(StringSession(os.environ["TG_SESSION"]), int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"]) as client:
        day = start
        while day <= today:
            msgs = fetch_day(client, day)
            print(f"{day}: {len(msgs)} posts -> {save_day(day, msgs).name}")
            day += dt.timedelta(days=1)


def main():
    today = dt.datetime.now(TZ).date()
    start = start_date(today)
    if "--check" in sys.argv:                       # quick look: newest posts as the parser sees them, nothing is written
        import web
        items, has = web.parse_page(web.get(f"https://t.me/s/{CHANNEL}"))
        print("page recognised:", has, "| posts on page:", len(items))
        for m in items[-3:]:
            print(m["id"], m["utc"].astimezone(TZ).strftime("%Y-%m-%d %H:%M"), "|", m["text"][:90].replace("\n", " "))
        return
    (pull_api if SOURCE == "api" else pull_web)(start, today)
    print(f"Done: {start} .. {today}")


if __name__ == "__main__":
    main()
