import json, os, sys, tempfile, unittest, subprocess, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import graph

ROWS = [
 {"id": 1, "date": "2026-10-10T08:00:00", "text": "RU strikes UA", "countries": ["ru", "ua"], "location": "UA", "category": "air",
  "arrows": [{"from": "RU", "to": "UA", "conf": 0.9, "kind": "physical"}]},
 {"id": 2, "date": "2026-10-11T08:00:00", "text": "RU again", "countries": ["RU", "UA"], "location": "UA", "category": "air",
  "arrows": [{"from": "RU", "to": "UA", "conf": 0.8, "kind": "physical"}]},
 {"id": 3, "date": "2026-10-12", "text": "Iran threatens", "countries": ["IR", "IL"], "category": "naval", "place": "Strait of Hormuz",
  "arrows": [{"attacker": "IR", "victim": "IL", "confidence": 0.95, "kind": "verbal"}]},
 {"id": 4, "date": "2026-10-12", "text": "no arrows", "countries": ["DE"]},
 {"id": 1, "date": "2026-10-10", "text": "RU strikes UA (edited)", "countries": ["RU", "UA"], "arrows": [{"from": "RU", "to": "UA", "conf": 0.9}]},
 {"id": 5, "date": "2026-10-13", "arrows": [{"from": "X", "to": "X", "conf": 1}]},
]

class T(unittest.TestCase):
    def test_build(self):
        n, e = graph.build(ROWS)
        ids = {x["id"] for x in n}
        self.assertIn("country:RU", ids); self.assertIn("place:strait_of_hormuz", ids)
        self.assertEqual(len([x for x in n if x["type"] == "post"]), 5)          # dedup id 1
        self.assertEqual(sum(x["type"] == "ATTACKED" for x in e), 2)             # self-arrow dropped, edited id1 once
        self.assertEqual(sum(x["type"] == "THREATENED" for x in e), 1)
        self.assertEqual(len([x for x in n if x["id"] == "post:1"]), 1)
        self.assertIn("edited", next(x for x in n if x["id"] == "post:1")["snippet"])
    def test_summary(self):
        s = graph.summarize(graph.build(ROWS)[1])
        top = s[0]
        self.assertEqual((top["source"], top["target"], top["count"]), ("country:RU", "country:UA", 2))
    def test_curated_wins(self):
        n, e = graph.build(ROWS, curated={"2": {"arrows": [{"from": "UA", "to": "RU", "conf": 1}]}})
        self.assertTrue(any(x["type"] == "ATTACKED" and x["source"] == "country:UA" for x in e))
    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "events.json")
            open(p, "w").write("\n".join(json.dumps(r) for r in ROWS) + "\nnot json\n")
            out = subprocess.run([sys.executable, os.path.join(ROOT, "src/graph.py"), "--events", p, "--curated", "none",
                                  "--out", d + "/g", "--html", d + "/graph.html"], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertTrue(os.path.exists(d + "/g/edges.json"))
            self.assertIn('"RU"', open(d + "/graph.html").read())
            self.assertNotIn("__DATA__", open(d + "/graph.html").read())

class RealFormat(unittest.TestCase):
    def test_real_format(self):
        with tempfile.TemporaryDirectory() as d:
            ev = {"version": 1, "posts": {
              "20134": {"c": ["IL", "LB"], "loc": "LB", "cat": "war", "ev": [{"from": "IL", "to": "LB", "kind": "physical", "confidence": 1.0, "why": "shelled"}]},
              "20137": {"c": ["RU", "US"], "loc": "US", "cat": "dip", "ev": [{"from": "US", "to": "RU", "kind": "verbal", "confidence": 1.0, "why": "bill"}]},
              "20152": {"c": ["IR"], "loc": None, "cat": "sea", "ev": [{"from": "IR", "to": None, "kind": "physical", "confidence": 1.0, "why": "missile"}]},
              "20135": {"c": [], "loc": None, "cat": "gen", "ev": []}}}
            json.dump(ev, open(d + "/events.json", "w"))
            json.dump([{"id": 20134, "date": "2026-10-12T09:00:00", "text": [{"type": "plain", "text": "Hello "}, "world"]}], open(d + "/result_old.json", "w"))
            meta = graph.load_meta(d)
            n, e = graph.build(graph.load(d + "/events.json"), meta=meta)
            self.assertEqual(sum(x["type"] == "ATTACKED" for x in e), 1)      # null target -> none
            self.assertEqual(sum(x["type"] == "THREATENED" for x in e), 1)
            p = next(x for x in n if x["id"] == "post:20134")
            self.assertEqual((p["date"], p["snippet"]), ("2026-10-12", "Hello world"))
            self.assertIn("category:war", {x["id"] for x in n})


# ---- graph page: arrows as the map has them, entities, hand overrides -------------------------------------------------
ENTS = [
    {"id": "person:trump", "type": "person", "name_en": "Donald Trump", "name_bg": "Тръмп", "aliases": ["Тръмп"]},
    {"id": "org:irgc", "type": "org", "name_en": "IRGC", "name_bg": "КСИР", "aliases": ["КСИР"]},
    {"id": "weapon:shahed", "type": "weapon", "name_en": "Shahed", "name_bg": "Шахед", "aliases": ["Шахед"]},
]
NOOV = {"mentions": {}, "entities": {}, "merge": {}, "keywords": {}}
META = {"1": ("ua", "war"), "2": ("me", "sea"), "3": ("", "gen")}             # (theme, category) of a post, as in the map rows
POSTS = [("1", "2026-09-30T10:00"), ("2", "2026-10-01T10:00"), ("3", "2026-10-02T10:00"), ("4", "2026-10-03T10:00")]
TEXTS = {"1": "Тръмп и КСИР", "2": "Тръмп каза, че Шахед и дрон летят", "3": "Шахеди над Киев", "4": "нищо"}


class MapRows(unittest.TestCase):
    def test_row_arrows_real_format(self):
        # 14-column map rows: [id, lat, lon, theme, conf, None, text, cat, arrows, date, att, inv, ex, [[from, to]]]
        a = [10, 11, 12, 13, "x", "p", "RU"]
        v = [10, 11, 12, 13, "x", "v", "US"]
        row = [1, 0, 0, "", "a", None, "t", "war", [a, v, a, a], "2026-10-01T10:00", [], [], 0, [["RU", "UA"], ["US", "IR"], ["RU", ""], ["IR", "?"]]]
        self.assertEqual(graph.row_arrows(row, "llm"), [("RU", "UA", "A", "l"), ("US", "IR", "T", "l")])   # open target and unknown target give no edge
        self.assertEqual(graph.row_arrows(row, "curated")[0][3], "c")
        self.assertEqual(graph.row_arrows(row, None)[0][3], "r")                                          # not in SRC = keyword rules
        self.assertEqual(graph.row_arrows(row[:13], "llm"), [])                                          # a row without the pairs column
        self.assertEqual(graph.row_arrows([1, 0, 0, "", "a", None, "t", "g", None, "d", [], [], 0, None], "llm"), [])

    def test_analyse_counts_match_matcher(self):
        an = graph.analyse(POSTS, TEXTS, {"1": [("US", "IR", "T", "l")]}, ENTS, NOOV, META)
        by = {e["id"]: len(an["ent_p"].get(i, [])) for i, e in enumerate(an["ents"])}
        self.assertEqual(by, {"org:irgc": 1, "person:trump": 2, "weapon:shahed": 2})
        self.assertEqual([r[0] for r in an["recs"]], [1, 2, 3])                          # post 4 has neither entity nor arrow
        self.assertEqual(an["months"], ["2026-09", "2026-10"])
        self.assertEqual(an["days"], [20260930, 20261001, 20261002])                        # every record also carries its day (page calendar and period slider)
        self.assertEqual(an["recs"][0][4], 20260930)
        t, o, w = (an["eix"][x] for x in ("person:trump", "org:irgc", "weapon:shahed"))
        self.assertEqual(sorted(an["pair_p"]), sorted([tuple(sorted(p)) for p in [(t, o), (t, w)]]))   # pair weight = posts with both
        self.assertEqual(an["th_tab"], ["ua", "me"]); self.assertEqual(an["ct_tab"], ["war", "sea", "gen"])
        self.assertEqual(an["recs"][1][5:7], [1, 1]); self.assertEqual(an["recs"][2][5:7], [-1, 2])   # theme/category are positions in the two tables, -1 = no theme

    def test_overrides(self):
        ov = {"mentions": {"2": {"exclude": ["person:trump"]}, "4": {"add": ["org:irgc"]}}, "entities": {"org:new": {"name_en": "New Org", "type": "org", "aliases": ["Киев"]},
              "weapon:shahed": {"name_bg": "Шахед-136"}}, "merge": {"org:irgc": "person:trump"}, "keywords": {"1": {"add": ["drones"]}}}
        an = graph.analyse(POSTS, TEXTS, {}, ENTS, ov, META)
        ids = [e["id"] for e in an["ents"]]
        self.assertNotIn("org:irgc", ids)                                               # merged away
        cnt = {e["id"]: len(an["ent_p"].get(i, [])) for i, e in enumerate(an["ents"])}
        self.assertEqual(cnt["person:trump"], 2)                                        # post 1 (twice, one mention), post 4 (added IRGC -> Trump); post 2 excluded
        self.assertEqual(cnt["org:new"], 1)                                             # new entity found by its alias (post 3)
        self.assertEqual(next(e for e in an["ents"] if e["id"] == "weapon:shahed")["name_bg"], "Шахед-136")

    def test_load_overrides_later_file_wins(self):
        with tempfile.TemporaryDirectory() as d:
            json.dump({"merge": {"a": "b"}, "mentions": {"1": {"exclude": ["x"]}}}, open(d + "/entity_overrides.json", "w"))
            json.dump({"merge": {"a": "c"}}, open(d + "/entity_overrides_2026-10-30.json", "w"))
            ov = graph.load_entity_overrides(d)
            self.assertEqual(ov["merge"], {"a": "c"}); self.assertEqual(ov["mentions"]["1"], {"exclude": ["x"]})
            self.assertEqual(graph.load_entity_overrides(d + "/none")["merge"], {})

    def test_pack_and_page(self):
        an = graph.analyse(POSTS, TEXTS, {"1": [("US", "IR", "T", "l")]}, ENTS, NOOV, META)
        data = graph.pack(an, {"US": "САЩ"}, 5)
        self.assertEqual(data["countries"], {"IR": "IR", "US": "САЩ"})
        import base64, gzip
        sn = json.loads(gzip.decompress(base64.b64decode(data["snz"])))
        self.assertEqual(sorted(sn), ["1", "2", "3"])                                    # every post in the page has its text, not only a few examples
        self.assertTrue(all(len(v[1]) <= 5 for v in sn.values())); self.assertEqual(sn["1"][0], "2026-09-30")
        ft = json.loads(gzip.decompress(base64.b64decode(data["ftz"])))
        self.assertEqual(ft[0], "тръмп и ксир")                                          # whole text, lower case, same order as "posts"
        self.assertEqual(len(ft), len(data["posts"])); self.assertEqual(data["themes"][0], ["ua", "Руско-украинска война"])
        self.assertEqual(graph.pack(an, {}, 5, False)["ftz"], "")
        html = graph.render_page(data, os.path.join(ROOT, "src", "graph_template.html"))
        self.assertNotIn("__DATA__", html); self.assertNotIn("__D3__", html); self.assertIn("САЩ", html)
        json.dumps(data)

    def test_cli_with_entities(self):
        with tempfile.TemporaryDirectory() as d:
            open(d + "/events.json", "w").write("\n".join(json.dumps(r) for r in ROWS))
            json.dump({"entities": ENTS}, open(d + "/entities.json", "w"))
            out = subprocess.run([sys.executable, os.path.join(ROOT, "src/graph.py"), "--events", d + "/events.json", "--curated", "none", "--entities", d + "/entities.json",
                                  "--out", d + "/g", "--html", d + "/graph.html"], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("entities", out.stdout)


class Countries(unittest.TestCase):
    NAMES = {"RU": "Русия", "UA": "Украйна", "IR": "Иран", "IL": "Израел", "US": "САЩ", "ML": "Мали", "EU": "ЕС", "NG": "Нигерия", "NE": "Нигер"}

    def test_flags(self):
        v = set(self.NAMES)
        self.assertEqual(graph.leading_flags("🇺🇦🇷🇺 ❗ Руски удар", v), ["UA", "RU"])
        self.assertEqual(graph.leading_flags("   🇺🇦 🇷🇺 текст", v), ["UA", "RU"])
        self.assertEqual(graph.leading_flags("Иран и 🇮🇱", v), [])                       # a flag after the first word is not a leading flag
        self.assertEqual(graph.all_flags("Иран и 🇮🇱 и 🇮🇱 и 🇽🇽", v), ["IL"])           # once; unknown codes dropped

    def test_names_in_text(self):
        m = graph.country_matcher(self.NAMES)
        ids = lambda s: [i[8:] for i in m.ids(s)]
        self.assertEqual(ids("Ирана и Израел, САЩ и ЕС"), ["IR", "IL", "US", "EU"])      # endings and acronyms
        self.assertEqual(ids("Нигерия и Нигер"), ["NG", "NE"])                          # the longer name wins
        self.assertEqual(ids("Мали и малки неща"), [])                                  # Мали is found by flag only
        self.assertEqual(ids("иран е лошо"), [])                                        # a capital is needed

    def test_meta_and_records(self):
        posts = [("1", "2026-10-01"), ("2", "2026-10-02"), ("3", "2026-10-03")]
        texts = {"1": "🇺🇦🇷🇺 Удар. Иран видя", "2": "Само Израел и САЩ", "3": "нищо"}
        cm = graph.country_meta(posts, texts, self.NAMES)
        self.assertEqual(cm["1"], (["UA", "RU"], [], ["IR"])); self.assertEqual(cm["2"], ([], [], ["IL", "US"])); self.assertNotIn("3", cm)
        an = graph.analyse(posts, texts, {}, ENTS, NOOV, None, cmeta=cm)
        self.assertEqual([r[0] for r in an["recs"]], [1, 2])                            # a post with only countries is in the page too
        self.assertEqual(an["recs"][0][7:], [["UA", "RU"], [], ["IR"]])
        self.assertEqual(sorted(graph.pack(an, self.NAMES)["countries"]), ["IL", "IR", "RU", "UA", "US"])


class CuratedFormat(unittest.TestCase):
    def test_build_curated_list_matches_by_text(self):          # needs the build.py imports (pycountry, ...); skipped where they are missing
        try:
            sys.path.insert(0, os.path.join(ROOT, "src")); import build
        except Exception as e:
            self.skipTest(f"build.py not importable here: {e}")
        cur = [[7, 1.0, 2.0, "x", "p", None, "Ракета удари Харков днес сутринта и още много текст", "war", [[1, 2, 3, 4, "Русия → Украйна", "p", "RU"]], "2026-01-01T00:00", [], [], 0]]
        out, lost = build.match_curated(cur, {20000: "Ракета удари Харков днес сутринта и още много текст"}, collections.Counter())
        self.assertEqual(list(out), [20000]); self.assertEqual(lost, [])


if __name__ == "__main__":
    unittest.main()
