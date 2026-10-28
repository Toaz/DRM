"""Offline tests for src/geo.py and for how build.py uses the place name the model found."""
import sys, collections, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import geo

CITIES = [
    dict(name="Kharkiv", alternatenames=["Kharkov", "Харків", "Харьков"], countrycode="UA", latitude=49.99, longitude=36.23, population=1400000),
    dict(name="Dnipro", alternatenames=["Dnipropetrovsk"], countrycode="UA", latitude=48.46, longitude=35.05, population=980000),
    dict(name="Paris", alternatenames=[], countrycode="FR", latitude=48.85, longitude=2.35, population=2100000),
    dict(name="Paris", alternatenames=[], countrycode="US", latitude=33.66, longitude=-95.55, population=25000),
    dict(name="Samara", alternatenames=[], countrycode="RU", latitude=53.2, longitude=50.15, population=1150000),
    dict(name="Samara", alternatenames=[], countrycode="CR", latitude=9.9, longitude=-85.5, population=3000),
]


class Gaz(unittest.TestCase):
    def setUp(self):
        self.g = geo.Gazetteer(CITIES)

    def test_names_ignore_case_accents_and_generic_words(self):
        self.assertEqual(geo.norm("Dnipró Oblast"), "dnipro")
        self.assertEqual(geo.norm("  City of Kharkiv "), "kharkiv")

    def test_alternative_names_are_found(self):
        self.assertEqual(self.g.find("Kharkov", "UA")[2], "UA")
        self.assertEqual(self.g.find("Харків", "UA")[2], "UA")

    def test_the_country_hint_picks_the_right_namesake(self):
        self.assertEqual(self.g.find("Samara", "RU")[:2], (53.2, 50.15))
        self.assertEqual(self.g.find("Paris", "US")[2], "US")

    def test_a_name_in_the_wrong_country_is_refused(self):
        self.assertIsNone(self.g.find("Kharkiv", "RU"))

    def test_without_a_hint_only_unique_names_are_accepted(self):
        self.assertIsNone(self.g.find("Paris"))
        self.assertEqual(self.g.find("Kharkiv")[2], "UA")

    def test_unknown_name_is_none(self):
        self.assertIsNone(self.g.find("Tolyattikauchuk plant", "RU"))


class PlaceFor(unittest.TestCase):
    def setUp(self):
        self.g = geo.Gazetteer(CITIES)

    def rec(self, pl, loc=None, to=()):
        return {"pl": pl, "loc": loc, "ev": [{"to": t} for t in to]}

    def test_no_place_no_answer(self):
        self.assertIsNone(geo.place_for(self.rec(None, "UA"), self.g))

    def test_location_is_tried_first_then_arrow_targets(self):
        self.assertEqual(geo.place_for(self.rec("Samara", "RU"), self.g)[2:], ("RU", "p"))
        self.assertEqual(geo.place_for(self.rec("Kharkiv", None, ["UA"]), self.g)[2], "UA")

    def test_blocs_are_not_countries(self):
        self.assertIsNone(geo.place_for(self.rec("Paris", "UN", ["EU"]), self.g))      # no hint left and two Parises

    def test_wrong_location_means_no_exact_place(self):
        self.assertIsNone(geo.place_for(self.rec("Kharkiv", "RU", ["RU"]), self.g))

    def test_distance(self):
        self.assertLess(geo.km((49.99, 36.23), (49.99, 36.23)), 1)
        self.assertAlmostEqual(geo.km((0, 0), (1, 0)), 111, delta=1)


try:
    import build
except ImportError:
    build = None


@unittest.skipIf(build is None, "geonamescache/pycountry not installed")
class BuildUsesModelPlace(unittest.TestCase):
    def setUp(self):
        self._gaz, self._on = build.GAZ, build.PLACE_FROM_LLM
        build.GAZ = geo.Gazetteer(CITIES)

    def tearDown(self):
        build.GAZ, build.PLACE_FROM_LLM = self._gaz, self._on

    def row(self, rec, L=None):
        stat = collections.Counter()
        return build.llm_row(rec, "text", "text", 1, "2026-10-01T10:00", 0, L, stat), stat

    REC = {"c": ["RU", "UA"], "loc": "UA", "cat": "war", "pl": "Kharkiv",
           "ev": [{"from": "RU", "to": "UA", "kind": "physical", "confidence": 1.0, "why": ""}]}

    def test_place_gives_an_exact_dot_and_arrow_end(self):
        r, stat = self.row(dict(self.REC))
        self.assertEqual(r[4], "p")
        self.assertAlmostEqual(r[1], 49.99, delta=0.5)
        self.assertAlmostEqual(r[8][0][2], r[1], places=2)         # the arrow ends where the dot is
        self.assertEqual(stat["place from model"], 1)

    def test_model_place_beats_the_keyword_city_list_and_the_difference_is_counted(self):
        r, stat = self.row(dict(self.REC), L=(50.45, 30.52, "UA", "p"))     # the keyword rules said Kyiv
        self.assertAlmostEqual(r[1], 49.99, delta=0.5)
        self.assertEqual(stat["place: model differs from city list (>150 km)"], 1)

    def test_unknown_place_keeps_the_old_behaviour(self):
        r, stat = self.row(dict(self.REC, pl="Some plant"), L=(50.45, 30.52, "UA", "p"))
        self.assertAlmostEqual(r[1], 50.45, delta=0.5)
        self.assertEqual(stat["place from model"], 0)

    def test_switch_turns_the_feature_off(self):
        build.PLACE_FROM_LLM = False
        r, _ = self.row(dict(self.REC))
        self.assertEqual(r[4], "a")                                 # country-level dot

    def test_post_without_arrows_is_also_placed_exactly(self):
        r, _ = self.row({"c": ["UA"], "loc": "UA", "cat": "dip", "pl": "Dnipro", "ev": []})
        self.assertEqual(r[4], "p")
        self.assertAlmostEqual(r[1], 48.46, delta=0.5)


if __name__ == "__main__":
    unittest.main()
