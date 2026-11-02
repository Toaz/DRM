import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import entities as E

DICT = [
    {"id": "person:trump", "type": "person", "name_en": "Donald Trump", "name_bg": "Тръмп", "aliases": ["Тръмп"]},
    {"id": "person:zelensky", "type": "person", "name_en": "Volodymyr Zelensky", "name_bg": "Володимир Зеленски", "aliases": ["Володимир Зеленски"]},
    {"id": "person:peskov", "type": "person", "name_en": "Dmitry Peskov", "name_bg": "Песков", "aliases": ["Песков"]},
    {"id": "person:katz", "type": "person", "name_en": "Israel Katz", "name_bg": "Кац", "aliases": ["Кац"]},
    {"id": "org:gru", "type": "org", "name_en": "GRU", "name_bg": "ГРУ", "aliases": ["ГРУ"]},
    {"id": "org:vsu", "type": "org", "name_en": "Ukrainian Armed Forces", "name_bg": "ВСУ", "aliases": ["ВСУ"]},
    {"id": "org:kremlin", "type": "org", "name_en": "Kremlin", "name_bg": "Кремъл", "aliases": ["Кремъл"]},
    {"id": "org:houthis", "type": "org", "name_en": "Houthis", "name_bg": "хуситите", "aliases": ["хуситите", "хусити"]},
    {"id": "org:lukoil", "type": "org", "name_en": "Lukoil", "name_bg": "Лукойл", "aliases": ["Лукойл"]},
    {"id": "org:helsing", "type": "org", "name_en": "Helsing", "name_bg": "Helsing", "aliases": ["Helsing"]},
    {"id": "weapon:shahed", "type": "weapon", "name_en": "Shahed", "name_bg": "Шахед", "aliases": ["Шахед"]},
    {"id": "weapon:grad", "type": "weapon", "name_en": "BM-21 Grad", "name_bg": "Град", "aliases": ["Град", "БМ-21"]},
    {"id": "weapon:s400", "type": "weapon", "name_en": "S-400", "name_bg": "С-400", "aliases": ["С-400"]},
    {"id": "weapon:tu95", "type": "weapon", "name_en": "Tu-95", "name_bg": "Ту-95", "aliases": ["Ту-95"]},
    {"id": "weapon:su30", "type": "weapon", "name_en": "Su-30", "name_bg": "Су-30", "aliases": ["Су-30"]},
    {"id": "weapon:b1", "type": "weapon", "name_en": "B-1", "name_bg": "B-1", "aliases": ["B-1"]},
    {"id": "weapon:centauro", "type": "weapon", "name_en": "B1 Centauro", "name_bg": "B1 Centauro", "aliases": ["B1 Centauro", "Centauro"]},
    {"id": "org:g7", "type": "org", "name_en": "G7", "name_bg": "Г-7", "aliases": ["Г-7", "G7", "Г7"]},
    {"id": "weapon:mi8", "type": "weapon", "name_en": "Mi-8", "name_bg": "Ми-8", "aliases": ["Ми-8"]},
    {"id": "weapon:kalibr", "type": "weapon", "name_en": "Kalibr", "name_bg": "Калибър", "aliases": ["Калибър"]},
    {"id": "org:hizb", "type": "org", "name_en": "Kataib Hizbullah", "name_bg": "Катаиб Хизбула", "aliases": ["Катаиб Хизбула"]},
    {"id": "org:hizb2", "type": "org", "name_en": "Hezbollah", "name_bg": "Хизбула", "aliases": ["Хизбула"]},
    {"id": "person:ben", "type": "person", "name_en": "Itamar Ben-Gvir", "name_bg": "Бен-Гвир", "aliases": ["Бен-Гвир", "Бен Гвир"]},
]
M = E.Matcher(DICT)


def got(text):
    return [(m["id"], m["text"]) for m in M.find(text)]


def idset(text):
    return M.ids(text)


class Words(unittest.TestCase):
    def test_endings(self):
        self.assertEqual(idset("Президентът Тръмп заяви. Тръмп също. Тръмпа не коментира. Тръмпът мълчи."), ["person:trump"])
        self.assertEqual(len(M.find("Тръмп, Тръмпа и Тръмпът")), 3)
        self.assertEqual(got("Шахеди и Шахедите летят")[0][1], "Шахеди")
        self.assertEqual(idset("пуснаха Калибри и Калибър"), ["weapon:kalibr"])

    def test_no_false_endings(self):
        self.assertEqual(idset("Кацане на летището"), [])  # Кац + ане
        self.assertEqual(idset("Каца в Хайфа"), ["person:katz"])

    def test_capital_needed_for_capitalised_alias(self):
        self.assertEqual(idset("ударът по град Киев и градушка"), [])
        self.assertEqual(idset("системата Град удари"), ["weapon:grad"])
        self.assertEqual(idset("доналд тръмп и тръмп"), [])
        self.assertEqual(idset("ТРЪМП заяви"), ["person:trump"])  # headline in capitals is fine

    def test_lowercase_alias_any_case(self):
        self.assertEqual(idset("Хуситите ударих, хуситите отговориха"), ["org:houthis"])

    def test_acronyms_exact(self):
        self.assertEqual(idset("мрежа на ГРУ и ВСУ"), ["org:gru", "org:vsu"])
        self.assertEqual(idset("грубо и Гру и ВСУта"), [])

    def test_multiword_and_longest(self):
        self.assertEqual(got("съобщи [Володимир Зеленски](https://x.com/ZelenskyyUa/status/1)"), [("person:zelensky", "Володимир Зеленски")])
        self.assertEqual(got("Катаиб Хизбула и Хизбула"), [("org:hizb", "Катаиб Хизбула"), ("org:hizb2", "Хизбула")])
        self.assertEqual(idset("Бен-Гвир и Бен Гвир и бен-гвир"), ["person:ben"])
        self.assertEqual(got("Кремъл Дмитрий Песков"), [("org:kremlin", "Кремъл"), ("person:peskov", "Песков")])

    def test_inside_hyphenated_word_and_latin(self):
        self.assertEqual(got("заводът \"Лукойл-Пермнефтеоргсинтез\" в Перм"), [("org:lukoil", "Лукойл")])
        self.assertEqual(idset("Rohde & Schwarz и Helsing (която"), ["org:helsing"])

    def test_links_and_tags_ignored(self):
        self.assertEqual(idset("виж https://x.com/Тръмп и t.me/Putin #Тръмп @Тръмп"), [])


class Designations(unittest.TestCase):
    def test_scripts_and_hyphen(self):
        for t in ("С-400", "C-400", "S-400", "с-400", "С400", "С 400", "S‑400"):
            self.assertEqual(idset(f"ударен {t} край"), ["weapon:s400"], t)
        for t in ("Ту-95МС", "ТУ-95", "TУ-95", "Tу-95", "Tu-95"):
            self.assertEqual(idset(f"бомбардировач {t} излетя"), ["weapon:tu95"], t)

    def test_suffix_but_not_longer_number(self):
        self.assertEqual(idset("Су-30СМ и Су-30"), ["weapon:su30"])
        self.assertEqual(len(M.find("Су-30СМ и Су-30")), 2)
        self.assertEqual(idset("хеликоптер Ми-80"), [])
        self.assertEqual(idset("хеликоптер Ми-8, Ми-8МТ"), ["weapon:mi8"])
        self.assertEqual(idset("в С-4000 не"), [])

    def test_one_letter_designations_keep_their_hyphen(self):
        self.assertEqual(idset("бомбардировач B-1 и B‑1"), ["weapon:b1"])
        self.assertEqual(got("бронирани машини B1 Centauro"), [("weapon:centauro", "B1 Centauro")])
        self.assertEqual(idset("витамин B1"), [])
        self.assertEqual(idset("срещата на Г7, G7 и Г-7"), ["org:g7"])
        self.assertEqual(len(M.find("срещата на Г7, G7 и Г-7")), 3)

    def test_inside_word(self):
        self.assertEqual(idset("АС-400"), [])


class Persons(unittest.TestCase):
    P = E.Matcher([
        {"id": "person:witkoff", "type": "person", "name_en": "Steve Witkoff", "name_bg": "Стив Уиткоф", "aliases": ["Стив Уиткоф"]},
        {"id": "person:bashar", "type": "person", "name_en": "Bashar al-Assad", "name_bg": "Башар Асад", "aliases": ["Башар Асад", "Асад"], "not_after": ["Рифат", "Хафез"]},
        {"id": "person:hafez", "type": "person", "name_en": "Hafez Assad", "name_bg": "Хафез Асад", "aliases": ["Хафез Асад"]},
        {"id": "person:ali", "type": "person", "name_en": "Ali Khamenei", "name_bg": "Али Хаменей", "aliases": ["Али Хаменей"]},
        {"id": "person:moj", "type": "person", "name_en": "Mojtaba Khamenei", "name_bg": "Моджтаба Хаменей", "aliases": ["Моджтаба Хаменей"]},
        {"id": "person:austin", "type": "person", "name_en": "Lloyd Austin", "name_bg": "Лойд Остин", "aliases": ["Лойд Остин"]},
    ])

    def test_surname_alone(self):
        self.assertEqual(self.P.ids("посещенията на Уиткоф и на Стив Уиткоф"), ["person:witkoff"])
        self.assertEqual(self.P.ids("посещенията на уиткоф"), [])  # capital needed

    def test_shared_or_banned_surname_is_not_derived(self):
        self.assertEqual(self.P.ids("заяви Хаменей"), [])  # Ali or Mojtaba?
        self.assertEqual(self.P.ids("в Остин, Тексас"), [])
        self.assertEqual(self.P.ids("Лойд Остин"), ["person:austin"])

    def test_not_after(self):
        self.assertEqual(self.P.ids("силите на Асад"), ["person:bashar"])
        self.assertEqual(self.P.ids("Рифат Асад е брат на Хафез Асад"), ["person:hafez"])
        self.assertEqual(self.P.ids("министърът Асад"), ["person:bashar"])


class Dictionary(unittest.TestCase):
    def test_name_en_and_collisions(self):
        self.assertEqual(idset("Donald Trump visited"), ["person:trump"])  # name_en counts as an alias
        m = E.Matcher(DICT + [{"id": "person:x", "type": "person", "name_en": "X", "name_bg": "Кац", "aliases": ["Кац"]}])
        self.assertEqual(m.collisions, {"Кац": ["person:katz", "person:x"]})
        self.assertEqual(m.ids("Кац каза"), ["person:katz"])  # the first entity wins

    def test_patterns(self):
        m = E.Matcher([{"id": "org:irgc", "type": "org", "name_en": "IRGC", "name_bg": "КСИР", "aliases": [], "patterns": [r"гвардейци\w* на ислямската революция"]}])
        self.assertEqual(m.ids("Корпусът на гвардейците на ислямската революция удари"), ["org:irgc"])


if __name__ == "__main__":
    unittest.main()
