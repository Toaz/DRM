"""Offline tests for tools/audit_map.py"""
import sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tools"))
import audit_map as A
import extract


def post(i, text):
    return {"id": i, "type": "message", "date": "2026-10-01T10:00:00", "text": text}


def rec(text, *events):
    return {"h": extract.text_hash(text), "pv": "x", "m": "m", "c": [], "loc": None, "cat": "war", "ev": list(events)}


def ev(f, t, c=1.0, kind="physical"):
    return {"from": f, "to": t, "kind": kind, "confidence": c, "why": "w"}


class Wilson(unittest.TestCase):
    def test_all_correct_still_leaves_room_for_error(self):
        lo, hi = A.wilson(40, 40)
        self.assertTrue(0.88 < lo < 0.93 and hi == 1.0)

    def test_empty_is_everything(self):
        self.assertEqual(A.wilson(0, 0), (0.0, 1.0))

    def test_half(self):
        lo, hi = A.wilson(50, 100)
        self.assertTrue(0.39 < lo < 0.41 and 0.59 < hi < 0.61)


class Sampling(unittest.TestCase):
    def setUp(self):
        t1, t2, t3, t4 = ("Russia struck Kharkiv with drones tonight.", "Talks start in Geneva next week about gas.",
                          "A missile hit a building somewhere overnight.", "Weak claim about a strike somewhere far away.")
        self.posts = [post(1, t1), post(2, t2), post(3, t3), post(4, t4)]
        self.cache = {"posts": {"1": rec(t1, ev("RU", "UA")), "2": rec(t2), "3": rec(t3), "4": rec(t4, ev("RU", "UA", c=0.3))}}

    def test_drawn_arrows_and_no_arrow_posts_are_separated(self):
        arrow, none = A.candidates(self.posts, self.cache)
        self.assertEqual([r["post_url"][-1] for r in arrow], ["1"])
        self.assertEqual(sorted(r["post_url"][-1] for r in none), ["2", "3", "4"])          # post 4: its only arrow is hidden

    def test_suspicious_no_arrow_posts_come_first(self):
        arrow, none = A.candidates(self.posts, self.cache)
        rows = A.pick(arrow, none, 4)                                                          # room for two no-arrow rows
        self.assertEqual({r["post_url"][-1] for r in rows if r["kind"] == "no arrow"}, {"3", "4"})
        rows = A.pick(arrow, none, 8)                                                          # room for four: fills up with the rest
        self.assertEqual({r["post_url"][-1] for r in rows if r["kind"] == "no arrow"}, {"2", "3", "4"})
        self.assertTrue(all("_suspicious" not in r for r in rows))

    def test_edited_posts_are_not_sampled(self):
        self.posts[0]["text"] = "Edited text that the model has not seen."
        arrow, _ = A.candidates(self.posts, self.cache)
        self.assertEqual(arrow, [])


class Scoring(unittest.TestCase):
    def test_only_marked_rows_count(self):
        rows = [{"kind": "arrow", "ok": "y"}, {"kind": "arrow", "ok": "n"}, {"kind": "arrow", "ok": ""},
                {"kind": "no arrow", "ok": "Y"}, {"kind": "no arrow", "ok": "maybe"}]
        self.assertEqual(A.score(rows), {"arrow": (1, 2), "no arrow": (1, 1)})


if __name__ == "__main__":
    unittest.main()
