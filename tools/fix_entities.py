"""Apply corrections to the saved LLM answers (data/entity_classified.json), then regroup with classify_entities.py --rebuild.

  python tools/fix_entities.py --dry      # what would change
  python tools/fix_entities.py            # apply
  python tools/classify_entities.py --rebuild

Why here and not in the candidates file: the answers are the source, so a fix survives every rebuild and the finished
phrases are never sent to the LLM again. Add your own lines to BY_NAME (every phrase the model named X) or BY_PHRASE
(one exact phrase). "other" removes a phrase from the dictionary, "media" lists it as a source (Reuters, Telegram).
"""
import sys, json, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from common import DATA

MINED, DONE = DATA / "entity_mined.json", DATA / "entity_classified.json"
OTHER, MEDIA = ["other", ""], ["media", ""]

BY_NAME = {}  # the name the model gave (any case) -> corrected [type, name]


def _many(ans, *names):
    for n in names:
        BY_NAME[n.casefold()] = ans


_many(MEDIA, "Reuters", "Financial Times", "Bloomberg", "CNN", "AFP", "The New York Times", "New York Times", "The Guardian",
      "The Times", "Al Jazeera", "The Economist", "The Wall Street Journal", "Wall Street Journal", "BBC", "Associated Press",
      "Fox News", "RIA Novosti", "Sky News", "Haaretz", "Al Arabiya", "NBC News", "Nikkei", "CBS News", "Middle East Eye", "Tasnim",
      "Bild", "Der Spiegel", "IRNA", "Le Monde", "Truth Social", "Kyiv Independent", "The Kyiv Independent", "Al Mayadeen",
      "ABC News", "Institute for the Study of War", "The Insider", "The Jerusalem Post", "Interfax", "CBS", "FARS", "RT", "Ynet",
      "Yonhap", "Kan 11", "Kyiv Post", "NBC", "L'Orient-Le Jour", "L'Orient Today", "Patreon", "Semafor", "The Atlantic",
      "Ambrey", "Die Welt", "Iran International", "RFE/RL", "Times of Israel", "Wafa", "Kommersant", "Nikkei Asia", "Journal",
      "Sky News Arabia", "Walla", "Flightradar24", "Telegram", "Twitter", "Facebook", "Instagram", "TikTok", "CSIS")
_many(OTHER, "De Re Militare", "Navy", "Ministry of Defense", "OSCE", "Arsenal", "Alternative for Germany", "UAE Forces", "SSC Azov",
      "PMC Wagner", "Total", "OpenAI", "The US", "Ministry of Interior", "VMZ", "Jalisco", "Wildberries", "Mohammed bin Salman",
      "Ahmed", "Mansur", "Sheikh Mansur", "Southern Military District", "Ground Forces", "Georgian Legion", "Sever", "Alpha",
      "Spetsnaz", "Iron Dome", "Virginia", "Strela-10", "K9 Thunder", "AN/TPQ-36", "Pegasus")
for old, new in {
    "BM-30 Smerch": "MLRS", 'ZRK "Strela-10"': "SAM system", "Gheran-2": "Geran-2", "Grad": "BM-21 Grad", "Bayraktar": "Bayraktar TB2",
    "Striker": "Stryker", "Abrams": "M1 Abrams", "MIM-104 Patriot": "Patriot", "JAS-39 Gripen": "Gripen", "Su-30SM": "Su-30",
    "SCALP": "Storm Shadow", "Caliber": "Kalibr", "M1A2 Abrams": "M1 Abrams", "Apache": "AH-64 Apache", "Bradley": "M2 Bradley", "F-35A": "F-35",
    "F-35 Lightning II": "F-35", "F-15E": "F-15", "MiG-31K": "MiG-31", "Tu-95MS": "Tu-95"}.items():
    _many(["weapon", new], old)
for old, new in {
    "Merkel": "Friedrich Merz", "Muktafa Sadir": "Muqtada al-Sadr", "Sadr": "Muqtada al-Sadr", "Piet Hegset": "Pete Hegseth",
    "Mark Carnie": "Mark Carney", "Dan Keane": "Dan Caine", "Katz": "Israel Katz", "Kyril Budanov": "Kyrylo Budanov",
    "Nasrallah": "Hassan Nasrallah", "Hasan Nasrallah": "Hassan Nasrallah", "Raisi": "Ebrahim Raisi", "Le Pen": "Marine Le Pen",
    "Umerov": "Rustem Umerov", "Aliyev": "Ilham Aliyev", "Ahmad al-Shara": "Ahmed al-Sharaa", "Recep Erdogan": "Recep Tayyip Erdoğan",
    "Volodymyr Zelenskyy": "Volodymyr Zelensky", "Mojtaba Hamenei": "Mojtaba Khamenei", "Georgia Meloni": "Giorgia Meloni",
    "Oleksandr Syrsky": "Oleksandr Syrskyi", "Maya Sandu": "Maia Sandu", "Smytrich": "Bezalel Smotrich", "Araghchi": "Abbas Araghchi",
    "Ben Gvir": "Itamar Ben-Gvir", "Surovikin": "Sergey Surovikin", "Nicolas Maduro": "Nicolás Maduro", "Barak Raviv": "Barak Ravid",
    "Petru Fiala": "Petr Fiala", "Bulgaria's Zelensky": "Volodymyr Zelensky", "Dmitry Medinsky": "Vladimir Medinsky",
    "Emil Efthimov": "Emil Eftimov"}.items():
    _many(["person", new], old)
_many(["unit", "Radwan Force"], "Raduan")
for old, new in {"IS": "Islamic State", "HTS": "Hayat Tahrir al-Sham", "VKS": "Russian Aerospace Forces", "VDV": "Russian Airborne Forces",
                 "STC": "Southern Transitional Council", "ENDF": "Ethiopian National Defense Force",
                 "ICE": "US Immigration and Customs Enforcement"}.items():
    _many(["org", new], old)

# Surface forms that must never become an alias (matched case-insensitively), whatever entry they landed in.
DROP_ALIASES = {"медина", "пески", "шара", "сирия ахмад", "конгрес", "урсула", "башар", "пен", "зелената", "зеленов", "хан", "будана"}

# Bulgarian full name for a person whose mined forms are all surname-only (used only then; most names are found automatically).
DISPLAY_BG = {
    "Ahmed al-Sharaa": "Ахмед ал-Шараа", "Muqtada al-Sadr": "Муктада ал-Садр", "Bashar al-Assad": "Башар Асад",
    "Marine Le Pen": "Марин льо Пен", "Ebrahim Raisi": "Ебрахим Раиси", "Hassan Nasrallah": "Хасан Насрала",
    "Dmitry Peskov": "Дмитрий Песков", "Volodymyr Zelensky": "Володимир Зеленски", "Israel Katz": "Исраел Кац",
    "Elon Musk": "Илон Мъск", "Viktor Orbán": "Виктор Орбан", "Ursula von der Leyen": "Урсула фон дер Лайен",
    "Pete Hegseth": "Пийт Хегсет", "Kyrylo Budanov": "Кирило Буданов", "Antony Blinken": "Антъни Блинкен",
    "Ilham Aliyev": "Илхам Алиев", "Itamar Ben-Gvir": "Итамар Бен-Гвир", "Rustem Umerov": "Рустем Умеров",
    "Robert Fico": "Роберт Фицо", "Nikol Pashinyan": "Никол Пашинян", "Ramzan Kadyrov": "Рамзан Кадиров",
    "Marco Rubio": "Марко Рубио", "Olaf Scholz": "Олаф Шолц", "Jair Bolsonaro": "Жаир Болсонаро",
    "Aleksandar Vučić": "Александър Вучич", "Yevgeny Prigozhin": "Евгений Пригожин", "Sergei Lavrov": "Сергей Лавров",
    "Vladimir Putin": "Владимир Путин", "Donald Trump": "Доналд Тръмп", "Benjamin Netanyahu": "Бенямин Нетаняху",
    "Friedrich Merz": "Фридрих Мерц", "Ali Khamenei": "Али Хаменей", "Mojtaba Khamenei": "Моджтаба Хаменей",
    "Lloyd Austin": "Лойд Остин", "Nicolás Maduro": "Николас Мадуро", "Steve Witkoff": "Стив Уиткоф",
    "Jared Kushner": "Джаред Кушнер", "Abbas Araghchi": "Абас Арагчи", "Sergei Shoigu": "Сергей Шойгу",
    "Khalifa Haftar": "Халифа Хафтар", "Bezalel Smotrich": "Безалел Смотрич", "Alexander Lukashenko": "Александър Лукашенко",
    "Vladimir Medinsky": "Владимир Медински", "Hafez Assad": "Хафез Асад", "Mark Rutte": "Марк Рюте",
}

BY_PHRASE = {  # exact mined phrase -> corrected answer (also settles phrases the model has not seen yet)
    "Хаят Тахрир": ["org", "Hayat Tahrir al-Sham"], "НОАК": ["org", "People's Liberation Army"], "ГУР": ["org", "HUR"],
    "ГРУ": ["org", "GRU"], "Мосад": ["org", "Mossad"], "Rheinmetall": ["org", "Rheinmetall"], "JNIM": ["org", "JNIM"],
    "Г-7": ["org", "G7"], "Г-20": ["org", "G20"],
    "Мерц": ["person", "Friedrich Merz"], "Фридрих Мерц": ["person", "Friedrich Merz"], "Марко Рубио": ["person", "Marco Rubio"],
    "Али Хаменей": ["person", "Ali Khamenei"], "Олаф Шолц": ["person", "Olaf Scholz"], "Николас Мадуро": ["person", "Nicolás Maduro"],
    "Виктор Орбан": ["person", "Viktor Orbán"], "Киър Стармър": ["person", "Keir Starmer"], "Лайен": ["person", "Ursula von der Leyen"],
    "Панцир": ["weapon", "Pantsir"], "С-400": ["weapon", "S-400"], "МиГ-29": ["weapon", "MiG-29"], "РСЗО": ["weapon", "MLRS"],
    "ТАСС": MEDIA, "Axios": MEDIA, "The Telegraph": MEDIA, "The Washington Post": MEDIA, "Washington Post": MEDIA,
    "Wall Street Journal": MEDIA, "Politico": MEDIA,
    "GPS": OTHER, "Starlink": OTHER, "Юн": OTHER, "Мансура": OTHER, "Салман": OTHER, "Ахмед": OTHER, "Шахид": OTHER, "Железен": OTHER,
    "Стрела": OTHER, "Кирил": OTHER, "Червения": OTHER, "Свобода": OTHER, "Антонов": OTHER, "Абдел Фатах": OTHER,
    "Panther": OTHER, "Hermes": OTHER, "Poseidon": OTHER, "Google": OTHER, "Microsoft": OTHER, "Amazon": OTHER, "Tesla": OTHER,
    "Ганц": ["person", "Benny Gantz"], "Либийската": OTHER, "Свободната": OTHER, "Корпуса": OTHER, "Феникс": OTHER, "Хан": OTHER,
    "ПКК Сирийски": OTHER, "Шор": ["person", "Ilan Shor"], "Зеленски": ["person", "Volodymyr Zelensky"], "Франциск": ["person", "Pope Francis"], "Организацията": OTHER, "Алианса": OTHER, "Алиансът": OTHER, "Алианс": OTHER, "МО": OTHER, "ВМС": OTHER,
}


def fix(items, done):
    """Returns {key: new answer} for the phrases that change."""
    out, seen = {}, set()
    for it in items:
        cur = done.get(it["key"])
        new = BY_NAME.get(cur[1].casefold()) if cur and cur[0] in ("person", "org", "unit", "weapon") else None
        if it["phrase"] in BY_PHRASE:
            new = BY_PHRASE[it["phrase"]]
            seen.add(it["phrase"])
        if new and cur != new:
            out[it["key"]] = new
    return out, [p for p in BY_PHRASE if p not in seen]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    items = json.load(open(MINED, encoding="utf-8"))["items"]
    saved = json.load(open(DONE, encoding="utf-8"))
    changes, unseen = fix(items, saved["done"])
    byk = {i["key"]: i["phrase"] for i in items}
    for k, v in list(changes.items())[:400]:
        if a.dry:
            print(byk[k], saved["done"].get(k, "(new)"), "->", v)
    print(f"{len(changes)} answers corrected; {len(unseen)} listed phrases are not in the mined file (fine if they are rare)")
    if a.dry:
        return
    saved["done"].update(changes)
    DONE.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", DONE, "- now run: python tools/classify_entities.py --rebuild")


if __name__ == "__main__":
    main()
