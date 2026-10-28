"""Pins the behaviour of the keyword rules in src/place.py (the fallback for posts the model has not read).

These cases were checked against the previous version of the file: a clean-up must not change them.
Needs geonamescache and pycountry (requirements.txt)."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
try:
    import place
except ImportError:
    place = None


@unittest.skipIf(place is None, "geonamescache/pycountry not installed")
class Rules(unittest.TestCase):
    def read(self, text):
        loc = place.locate(text)
        det = place.detect(text, loc[2] if loc else None)
        return (loc[2], loc[3]) if loc else None, (det[0], det[1][2], det[2]) if det else None

    def test_active_sentence_attacker_before_the_verb(self):
        self.assertEqual(self.read("Русия нанесе удар по Харков с дронове тази нощ."), (("UA", "p"), ("RU", "UA", "p")))

    def test_attack_on_a_russian_city_goes_the_other_way(self):
        self.assertEqual(self.read("Украински дронове атакуваха рафинерията в Самара."), (("RU", "p"), ("UA", "RU", "p")))

    def test_passive_sentence_attacker_after_the_verb(self):
        self.assertEqual(self.read("Харков е бил ударен от Русия през нощта."), (("UA", "p"), ("RU", "UA", "p")))

    def test_middle_east(self):
        self.assertEqual(self.read("Израел удари позиции на Хизбула в южен Ливан."), (("LB", "p"), ("IL", "LB", "p")))

    def test_deliveries_and_signed_deals_are_not_attacks(self):
        self.assertEqual(self.read("Германия ще достави на Украйна системи за ПВО, договорът е подписан.")[1], None)

    def test_a_reference_to_an_earlier_strike_is_not_a_new_one(self):
        self.assertEqual(self.read("След удара по Киев, кадри от атаката показват пожар.")[1], None)

    def test_diplomacy_gets_a_place_but_no_arrow(self):
        self.assertEqual(self.read("Среща на министрите в Брюксел за санкциите."), (("EU", "p"), None))

    def test_flags_and_names_give_a_country_when_no_city_is_named(self):
        self.assertEqual(place.locate("🇵🇱 Полша обяви нови разходи за отбрана.")[2:], ("PL", "a"))

    def test_nothing_recognisable_gives_none(self):
        self.assertIsNone(place.locate("Няма нищо познато в този текст."))

    def test_word_boundaries(self):
        # "уфа" (a city) must not match inside another word
        self.assertIsNone(place.locate("Той е кръстен Муфасаил на баба си."))


if __name__ == "__main__":
    unittest.main()
