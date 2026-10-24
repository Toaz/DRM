"""Offline tests for src/extract.py (no network, no API key).   Run:  python -m unittest discover -s tests -v"""
import sys, json, tempfile, threading, unittest, http.server
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import extract
from extract import clean_events, parse, record, waiting, enrich, load_cache, save_cache, LLMError, QuotaExceeded


def ev(f, t, kind="physical", c=1.0):
    return {"from": f, "to": t, "kind": kind, "confidence": c, "why": ""}


def answer(*events, location="UA", countries=("RU", "UA")):
    return json.dumps({"countries": list(countries), "location": location, "category": "war", "events": list(events)})


def post(i, text="Russia launched drones at Kharkiv overnight."):
    return {"id": i, "type": "message", "date": "2026-10-01T10:00:00", "text": text}


class CleanEvents(unittest.TestCase):
    def test_duplicates_collapse(self):
        self.assertEqual(len(clean_events({"events": [ev("IL", "SY"), ev("IL", "SY")]})), 1)

    def test_no_arrow_from_a_country_to_itself(self):
        self.assertEqual(clean_events({"events": [ev("SY", "SY", "verbal", 0.9)]}), [])

    def test_missing_target_falls_back_to_location_but_never_to_the_attacker(self):
        self.assertEqual(clean_events({"location": "UA", "events": [ev("RU", None)]})[0]["to"], "UA")
        r = clean_events({"location": "IR", "events": [ev("IR", None)]})       # location is the attacker itself: target stays open
        self.assertEqual([(e["from"], e["to"]) for e in r], [("IR", None)])

    def test_named_attacker_without_a_target_country_is_kept_open(self):
        r = clean_events({"location": None, "events": [ev("IR", None)]})
        self.assertEqual([(e["from"], e["to"], e["show"]) for e in r], [("IR", None, True)])

    def test_open_target_only_for_physical_attacks(self):
        self.assertEqual(clean_events({"events": [ev("IR", None, "verbal", 0.95)]}), [])

    def test_open_target_still_needs_a_valid_attacker(self):
        self.assertEqual(clean_events({"events": [ev("", None), ev("xx", None), ev(None, None)]}), [])

    def test_physical_beats_verbal_for_the_same_pair(self):
        r = clean_events({"events": [ev("US", "IR", "verbal", 0.95), ev("US", "IR", "physical", 0.85)]})
        self.assertEqual([(e["kind"]) for e in r], ["physical"])

    def test_thresholds_hide_weak_arrows(self):
        r = clean_events({"events": [ev("US", "IR", c=0.5), ev("RU", "UA", c=0.7), ev("CN", "TW", "verbal", 0.85)]})
        self.assertEqual([e["show"] for e in r], [False, True, False])   # physical needs 0.7, verbal needs 0.9

    def test_invented_codes_and_bad_kinds_are_dropped(self):
        bad = [{"from": "USA", "to": "IR", "kind": "physical"}, {"from": "us", "to": "IR", "kind": "physical"},
               {"from": "US", "to": "IR", "kind": "other"}, {"to": "IR", "kind": "physical"}, "junk", None]
        self.assertEqual(clean_events({"events": bad}), [])

    def test_location_must_be_a_country_not_a_bloc(self):
        r = clean_events({"location": "EU", "events": [ev("RU", None)]})
        self.assertEqual([e["to"] for e in r], [None])        # a bloc is never used as the target; the arrow stays open


class Parse(unittest.TestCase):
    def test_markdown_fences_and_chatter_are_tolerated(self):
        raw = "Sure!\n```json\n" + answer(ev("RU", "UA")) + "\n```"
        self.assertEqual(parse(raw)["events"][0]["from"], "RU")

    def test_garbage_raises_value_error(self):
        with self.assertRaises(ValueError):
            parse("no json here")


class Cache(unittest.TestCase):
    def test_roundtrip_one_post_per_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "events.json"
            c = {"version": 1, "posts": {"20": {"c": ["UA"]}, "3": {"c": ["RU"]}}}
            save_cache(c, p)
            self.assertEqual(load_cache(p), c)
            self.assertEqual(len(p.read_text(encoding="utf-8").strip().splitlines()), 4)   # header, 2 posts, footer
            self.assertFalse(p.with_suffix(".tmp").exists())

    def test_missing_file_gives_empty_cache(self):
        self.assertEqual(load_cache(Path(tempfile.gettempdir()) / "nope-events.json")["posts"], {})


class Enrich(unittest.TestCase):
    def run_enrich(self, posts, cache, call, **kw):
        return enrich(posts, cache, call, "test/model", sleep=0, **kw)

    def test_each_post_is_sent_once(self):
        posts, cache, calls = [post(1), post(2)], {"version": 1, "posts": {}}, []
        def call(t):
            calls.append(t)
            return answer(ev("RU", "UA"))
        self.assertEqual(self.run_enrich(posts, cache, call)["done"], 2)
        self.assertEqual(self.run_enrich(posts, cache, call)["done"], 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(cache["posts"]["1"]["ev"][0]["from"], "RU")

    def test_edited_post_is_read_again_but_a_new_prompt_does_not_redo_old_posts(self):
        cache = {"version": 1, "posts": {}}
        self.run_enrich([post(1)], cache, lambda t: answer(ev("RU", "UA")))
        self.assertEqual(waiting([post(1, "Russia launched drones at Odesa.")], cache)[0]["id"], 1)   # text changed
        cache["posts"]["1"]["pv"] = "old-prompt"
        self.assertEqual(waiting([post(1)], cache), [])

    def test_newest_first_and_limit(self):
        seen = []
        def call(t):
            seen.append(t)
            return answer()
        posts = [post(i, f"post number {i} about the war") for i in (1, 2, 3, 4)]
        self.run_enrich(posts, {"version": 1, "posts": {}}, call, limit=2)
        self.assertEqual(seen, ["post number 4 about the war", "post number 3 about the war"])

    def test_quota_stops_quietly_and_keeps_what_was_done(self):
        n = []
        def call(t):
            n.append(1)
            if len(n) > 2:
                raise QuotaExceeded("daily limit")
            return answer(ev("RU", "UA"))
        cache = {"version": 1, "posts": {}}
        st = self.run_enrich([post(i, f"post number {i} about a drone attack") for i in range(1, 6)], cache, call)
        self.assertTrue(st["quota"])
        self.assertEqual(len(cache["posts"]), 2)

    def test_three_failures_in_a_row_stop_the_run(self):
        n = []
        def call(t):
            n.append(1)
            raise LLMError("boom")
        st = self.run_enrich([post(i, f"post number {i} about a drone attack") for i in range(1, 9)], {"version": 1, "posts": {}}, call)
        self.assertEqual((st["failed"], len(n)), (3, 3))

    def test_unparseable_answer_is_not_stored(self):
        cache = {"version": 1, "posts": {}}
        st = self.run_enrich([post(1)], cache, lambda t: "I cannot do that")
        self.assertEqual((st["unparseable"], cache["posts"]), (1, {}))

    def test_removed_record_is_read_again(self):
        cache = {"version": 1, "posts": {}}
        self.run_enrich([post(1)], cache, lambda t: answer(ev("RU", None)))
        self.assertEqual(waiting([post(1)], cache), [])
        cache["posts"].pop("1")                                   # what --redo does
        self.assertEqual(len(waiting([post(1)], cache)), 1)

    def test_short_posts_are_ignored(self):
        self.assertEqual(waiting([post(1, "ok")], {"version": 1, "posts": {}}), [])

    def test_record_contents(self):
        r = record(answer(ev("RU", "UA"), ev("RU", "RU"), countries=("RU", "UA", "XX1", "ua")), "text", "m")
        self.assertEqual((r["c"], r["loc"], r["cat"], len(r["ev"])), (["RU", "UA"], "UA", "war", 1))
        self.assertNotIn("show", r["ev"][0])


class FakeAPI(http.server.BaseHTTPRequestHandler):
    mode = "ok"
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        if self.mode == "quota":
            self.send_response(429); self.send_header("Retry-After", "500"); self.end_headers(); self.wfile.write(b"daily limit"); return
        if self.mode == "badkey":
            self.send_response(401); self.end_headers(); self.wfile.write(b"bad key"); return
        body = json.dumps({"choices": [{"message": {"content": answer(ev("RU", "UA"))}}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a):
        pass


class AskOverHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), FakeAPI)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_normal_answer(self):
        FakeAPI.mode = "ok"
        self.assertEqual(parse(extract.ask("text", "m", "k", self.url))["events"][0]["to"], "UA")

    def test_long_retry_after_means_quota_exceeded(self):
        FakeAPI.mode = "quota"
        with self.assertRaises(QuotaExceeded):
            extract.ask("text", "m", "k", self.url)

    def test_bad_key_is_a_clear_error(self):
        FakeAPI.mode = "badkey"
        with self.assertRaises(LLMError) as cm:
            extract.ask("text", "m", "k", self.url)
        self.assertIn("401", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
