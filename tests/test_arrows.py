"""Offline tests for src/arrows.py and the model branch of build.py.   Run:  python -m unittest discover -s tests -v"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import arrows as AR

PT = {"RU": (55.0, 37.0), "UA": (49.0, 32.0), "PL": (52.0, 21.0), "MD": (47.0, 28.9), "IR": (32.0, 53.0), "US": (38.9, -77.0)}


def ev(f, t, kind="physical", c=1.0, show=True):
    return {"from": f, "to": t, "kind": kind, "confidence": c, "show": show}


def ids(iso):
    return {"RU": ["643"], "UA": ["804"], "PL": ["616"], "MD": ["498"], "IR": ["364"], "US": ["840"], "EU": ["040", "056"]}.get(iso, [])


class Visible(unittest.TestCase):
    def test_hidden_arrows_are_dropped_and_physical_comes_first(self):
        r = AR.visible([ev("A", "B", "verbal", 0.99), ev("C", "D", c=0.8), ev("E", "F", c=0.9), ev("G", "H", show=False)])
        self.assertEqual([(e["from"], e["to"]) for e in r], [("E", "F"), ("C", "D"), ("A", "B")])


class Plan(unittest.TestCase):
    def test_several_arrows_end_in_their_own_countries(self):
        arr, skipped = AR.plan([ev("RU", "PL"), ev("RU", "MD")], PT)
        self.assertEqual([(a["from"], a["to"], a["dest"]) for a in arr], [("RU", "PL", PT["PL"]), ("RU", "MD", PT["MD"])])
        self.assertEqual(skipped, [])

    def test_exact_place_is_used_only_for_the_country_it_lies_in(self):
        place = (50.0, 36.2, "UA", "p")                          # a city in Ukraine
        arr, _ = AR.plan([ev("RU", "UA"), ev("RU", "PL")], PT, place)
        self.assertEqual((arr[0]["dest"], arr[0]["conf"]), ((50.0, 36.2), "p"))
        self.assertEqual((arr[1]["dest"], arr[1]["conf"]), (PT["PL"], "a"))

    def test_unknown_country_skips_only_that_arrow(self):
        arr, skipped = AR.plan([ev("RU", "UA"), ev("RU", "XX"), ev("XX", "UA")], PT)
        self.assertEqual(len(arr), 1)
        self.assertEqual(len(skipped), 2)

    def test_verbal_kind_is_marked_v(self):
        self.assertEqual(AR.plan([ev("US", "IR", "verbal", 0.95)], PT)[0][0]["kind"], "v")


class OpenTarget(unittest.TestCase):
    HORMUZ = (26.57, 56.25, "IR", "p")                            # exact place found in the post, tagged with a country

    def test_attacker_without_target_is_drawn_to_the_exact_place(self):
        arr, skipped = AR.plan([ev("IR", None)], PT, self.HORMUZ)
        self.assertEqual(skipped, [])
        self.assertEqual((arr[0]["from"], arr[0]["dest"], arr[0]["conf"], arr[0]["open"]), ("IR", (26.57, 56.25), "p", True))

    def test_without_an_exact_place_no_arrow(self):
        arr, skipped = AR.plan([ev("IR", None)], PT, None)
        self.assertEqual((arr, len(skipped)), ([], 1))

    def test_normal_arrows_are_not_marked_open(self):
        arr, _ = AR.plan([ev("RU", "UA")], PT, self.HORMUZ)
        self.assertFalse(arr[0]["open"])

    def test_open_and_normal_arrows_can_share_a_post(self):
        arr, _ = AR.plan([ev("RU", "UA"), ev("RU", None)], PT, self.HORMUZ)
        self.assertEqual([a["open"] for a in arr], [False, True])


class Order(unittest.TestCase):
    def test_arrow_into_the_event_country_comes_first(self):
        arr, _ = AR.plan([ev("IR", "US"), ev("US", "IR")], PT)
        self.assertEqual([a["to"] for a in AR.main_first(arr, "IR")], ["IR", "US"])
        self.assertEqual([a["to"] for a in AR.main_first(arr, None)], ["US", "IR"])      # no location: order unchanged


class CountryIds(unittest.TestCase):
    def test_attackers_in_arrow_order_targets_first_then_mentioned_without_duplicates(self):
        arr, _ = AR.plan([ev("RU", "PL"), ev("RU", "MD")], PT)
        att, inv = AR.country_ids(arr, ["PL", "US", "RU", "EU"], ids, "PL")
        self.assertEqual(att, ["643"])
        self.assertEqual(inv, ["616", "498", "840", "643", "040", "056"])

    def test_no_arrows_uses_location_then_mentioned(self):
        self.assertEqual(AR.country_ids([], ["IR", "US"], ids, "UA"), ([], ["804", "364", "840"]))


try:
    import build                                              # needs geonamescache and pycountry (requirements.txt)
except ImportError:
    build = None


@unittest.skipIf(build is None, "geonamescache/pycountry not installed")
class ModelRow(unittest.TestCase):
    def rec(self, ev_list, loc="PL", c=("PL", "RU")):
        return {"c": list(c), "loc": loc, "cat": "air", "ev": ev_list}

    def row(self, rec, L=None):
        stat = __import__("collections").Counter()
        r = build.llm_row(rec, "text of a post", "text of a post", 1, "2026-10-01T10:00", 0, L, stat)
        return r, stat

    def test_two_arrows_one_dot_in_the_event_country(self):
        r, stat = self.row(self.rec([{"from": "RU", "to": "PL", "kind": "physical", "confidence": 1.0, "why": ""},
                                     {"from": "RU", "to": "MD", "kind": "physical", "confidence": 0.9, "why": ""}]))
        self.assertEqual(len(r[8]), 2)
        self.assertEqual([a[6] for a in r[8]], ["RU", "RU"])
        self.assertTrue(stat["post with several arrows"])
        self.assertEqual(r[10], build.ids("RU"))

    def test_open_target_arrow_goes_to_the_place_and_has_a_readable_label(self):
        r, _ = self.row(self.rec([{"from": "IR", "to": None, "kind": "physical", "confidence": 0.95, "why": ""}], loc=None, c=("IR",)),
                        L=(26.57, 56.25, "IR", "p"))
        self.assertEqual(len(r[8]), 1)
        self.assertEqual((r[8][0][6], r[8][0][4].endswith(build.OPEN_TARGET)), ("IR", True))
        self.assertAlmostEqual(r[1], 26.57, delta=0.5)             # the dot sits at the place (plus a small jitter)

    def test_open_target_without_a_place_is_not_drawn(self):
        r, stat = self.row(self.rec([{"from": "IR", "to": None, "kind": "physical", "confidence": 0.95, "why": ""}], loc=None, c=("IR",)))
        self.assertTrue(r is None or r[8] is None)
        self.assertEqual(stat["arrows skipped (no coordinates)"], 1)

    def test_weak_arrows_are_hidden_not_drawn(self):
        r, stat = self.row(self.rec([{"from": "US", "to": "IR", "kind": "physical", "confidence": 0.5, "why": ""}], loc="IR", c=("US", "IR")))
        self.assertIsNone(r[8])                                # None, not [], because the page tests this value
        self.assertEqual(stat["hidden arrows"], 1)

    def test_no_arrow_post_is_placed_by_the_country_the_model_named(self):
        r, _ = self.row(self.rec([], loc="PL"))
        self.assertIsNone(r[8])
        self.assertEqual(r[4], "a")
        self.assertEqual(r[11][0], build.ids("PL")[0])

    def test_post_with_no_place_at_all_gives_none(self):
        r, _ = self.row(self.rec([], loc=None, c=()))
        self.assertIsNone(r)


if __name__ == "__main__":
    unittest.main()
