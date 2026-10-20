"""Shared helpers: paths, reading the old export plus the daily files."""
import json, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def txt(m):
    """Message text as a plain string (Telegram exports may store it as a list of parts)."""
    t = m.get("text", "")
    if isinstance(t, list):
        return "".join(p if isinstance(p, str) else p.get("text", "") for p in t)
    return t


def daily_files():
    """result_DD.MM.YYYY.json files sorted by real date (plain string sort would be wrong)."""
    fs = DATA.glob("result_??.??.????.json")
    return sorted(fs, key=lambda f: dt.datetime.strptime(f.stem[7:], "%d.%m.%Y"))


def load_all():
    """All posts: result_old.json first, then every daily file; a later file wins for the same post id."""
    posts = {}
    for f in [DATA / "result_old.json"] + daily_files():
        if not f.exists():
            continue
        with open(f, encoding="utf-8") as fh:
            msgs = json.load(fh)["messages"]
        for m in msgs:
            if m.get("type", "message") == "message":
                posts[m["id"]] = m
    return sorted(posts.values(), key=lambda m: m["id"])
