"""Offline tests (no network, no Telegram).   Run:  python -m unittest discover -s tests -v"""
import sys, json, tempfile, datetime as dt, unittest
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common, pull, web

TZ, UTC = ZoneInfo("Europe/Sofia"), dt.timezone.utc


def page(posts):
    """Imitates one page of t.me/s/<channel>: oldest post first, flags as <i class="emoji"><b>..</b></i>."""
    boxes = ""
    for i, t, txt in posts:
        body = txt.replace("\n", "<br/>").replace("\U0001F1FA\U0001F1E6", '<i class="emoji"><b>\U0001F1FA\U0001F1E6</b></i>')
        boxes += (f'<div class="tgme_widget_message_wrap"><div class="tgme_widget_message text_not_supported_wrap" data-post="ch/{i}">'
                  f'<div class="tgme_widget_message_bubble"><div class="tgme_widget_message_text js-message_text" dir="auto">{body}</div>'
                  f'<span class="tgme_widget_message_meta"><a class="tgme_widget_message_date" href="https://t.me/ch/{i}">'
                  f'<time datetime="{t.isoformat()}" class="time">x</time></a></span></div></div></div>')
    return f"<html><body><section>{boxes}</section></body></html>"


def fake_channel(n=70, newest=dt.datetime(2026, 10, 13, 20, 0, tzinfo=UTC)):
    posts = [(100 + k, newest - dt.timedelta(hours=k * 1.5), f"post {100 + k}") for k in range(n)]   # ids ascending = time ascending
    posts = sorted([(i, newest - dt.timedelta(hours=(n - 1 - (i - 100)) * 1.5), f"post {i}") for i, _, _ in posts])
    def fetch(url):
        before = int(url.split("before=")[1]) if "before=" in url else 10 ** 9
        return page([p for p in posts if p[0] < before][-20:])
    return posts, fetch


class Web(unittest.TestCase):
    def test_parse_keeps_flags_and_newlines(self):
        items, has = web.parse_page(page([(7, dt.datetime(2026, 10, 12, 16, 55, tzinfo=UTC), "\u2757\U0001F1FA\U0001F1E6 \u0410\n\u0411")]))
        self.assertTrue(has)
        self.assertEqual(items[0]["text"], "\u2757\U0001F1FA\U0001F1E6 \u0410\n\u0411")
        self.assertEqual(items[0]["id"], 7)

    def test_crawl_stops_at_start_and_pages_backwards(self):
        posts, fetch = fake_channel()
        start = dt.datetime(2026, 10, 12, 0, 0, tzinfo=TZ)
        got = web.crawl("ch", start, TZ, delay=0, fetch=fetch)
        ids = sorted(m["id"] for m in got)
        self.assertTrue(all(i in ids for i, t, _ in posts if t.astimezone(TZ) >= start))   # nothing in the window is missed
        self.assertLess(len(ids), 70)                                                      # and it did not read everything

    def test_layout_change_fails_loudly(self):
        with self.assertRaises(RuntimeError):
            web.crawl("ch", dt.datetime(2026, 10, 12, tzinfo=TZ), TZ, delay=0, fetch=lambda u: "<html>nothing here</html>")

    def test_page_limit_fails_loudly(self):
        _, fetch = fake_channel()
        with self.assertRaises(RuntimeError):
            web.crawl("ch", dt.datetime(2000, 1, 1, tzinfo=TZ), TZ, max_pages=2, delay=0, fetch=fetch)


class Files(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        common.DATA = pull.DATA = self.tmp
        json.dump({"messages": [{"id": 1, "type": "message", "date": "2026-10-12T19:55:00", "text": "old"}]}, open(self.tmp / "result_old.json", "w"))

    def test_pull_web_writes_one_file_per_day_in_local_time(self):
        posts, fetch = fake_channel()
        crawler = lambda ch, s, tz, max_pages: web.crawl(ch, s, tz, max_pages, delay=0, fetch=fetch)
        pull.pull_web(dt.date(2026, 10, 12), dt.date(2026, 10, 13), crawler=crawler)
        names = sorted(p.name for p in self.tmp.glob("result_*.json"))
        self.assertEqual(names, ["result_12.10.2026.json", "result_13.10.2026.json", "result_old.json"])
        d13 = json.load(open(self.tmp / "result_13.10.2026.json"))["messages"]
        self.assertTrue(all(m["date"].startswith("2026-10-13") for m in d13))        # Sofia time, not UTC
        again = {p.name: p.read_bytes() for p in self.tmp.glob("result_1*.json")}
        pull.pull_web(dt.date(2026, 10, 12), dt.date(2026, 10, 13), crawler=crawler)  # second run overwrites, identical
        self.assertEqual(again, {p.name: p.read_bytes() for p in self.tmp.glob("result_1*.json")})
        self.assertEqual(list(self.tmp.glob("*.tmp")), [])

    def test_failed_crawl_leaves_existing_files_untouched(self):
        pull.save_day(dt.date(2026, 10, 13), [{"id": 5, "type": "message", "date": "2026-10-13T10:00:00", "text": "keep me"}])
        bad = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("layout changed"))
        with self.assertRaises(RuntimeError):
            pull.pull_web(dt.date(2026, 10, 12), dt.date(2026, 10, 13), crawler=bad)
        self.assertIn("keep me", (self.tmp / "result_13.10.2026.json").read_text())

    def test_start_date_and_merge_order(self):
        self.assertEqual(pull.start_date(dt.date(2026, 10, 14)), dt.date(2026, 10, 12))     # fills the gap since the old export
        json.dump({"messages": [{"id": 2, "type": "message", "date": "2026-10-14T01:00:00", "text": "v1"}]}, open(self.tmp / "result_14.10.2026.json", "w"))
        json.dump({"messages": [{"id": 2, "type": "message", "date": "2026-10-14T01:00:00", "text": "v2"}, {"id": 3, "type": "message", "date": "2026-11-02T09:00:00", "text": "n"}]}, open(self.tmp / "result_02.11.2026.json", "w"))
        self.assertEqual([f.name for f in common.daily_files()], ["result_14.10.2026.json", "result_02.11.2026.json"])  # by date, not text
        self.assertEqual({m["id"]: m["text"] for m in common.load_all()}, {1: "old", 2: "v2", 3: "n"})


if __name__ == "__main__":
    unittest.main()
