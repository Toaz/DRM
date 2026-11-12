import sys, json, unittest, threading, http.server
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in ("src", "tools"):
    sys.path.insert(0, str(ROOT / p))
import extract, mine_entities as M, classify_entities as C, promote_entities as P, fix_entities as F


def post(i, text):
    return {"id": i, "type": "message", "date": "2026-01-01T10:00:00", "text": text}


class Mine(unittest.TestCase):
    def posts(self):
        ps, n = [], 0
        for _ in range(20):  # a generic sentence opener, always capitalised at the start
            n += 1; ps.append(post(n, "Министерството на отбраната съобщи нещо важно днес за ситуацията."))
            n += 1; ps.append(post(n, "Министерството обяви нови мерки по повод ситуацията на фронта."))
            n += 1; ps.append(post(n, "Днес е ден за новини от фронта, а всички мълчат."))
            n += 1; ps.append(post(n, "Според експерти положението е сложно, но не и безнадеждно."))
        for k in range(5):
            n += 1; ps.append(post(n, f"Днес Доналд Тръмп говори пред медиите {k} пъти за темата."))
            n += 1; ps.append(post(n, "Според Путин преговорите продължават, а Тръмпа не коментира нищо повече."))
            n += 1; ps.append(post(n, "Изтребители F-16 и С-400 бяха видени, а S-400 остана. Ми-8 кацна, COVID-19 мина."))
        n += 1; ps.append(post(n, "Зеленски заяви нещо кратко и ясно днес."))  # one initial-only mention
        return ps

    def test_designations_and_folding(self):
        it = {i["key"]: i for i in M.mine(self.posts(), min_count=3)}
        self.assertIn("d:F-16", it)
        self.assertEqual(it["d:C-400"]["posts"], 5)  # С-400 with Cyrillic С
        self.assertIn("d:S-400", it)
        self.assertIn("d:MИ-8", it)
        self.assertFalse([k for k in it if k.startswith("d:") and "OVID" in k])

    def test_names_inflection_and_openers(self):
        it = {i["phrase"]: i for i in M.mine(self.posts(), min_count=3)}
        self.assertIn("Доналд Тръмп", it)
        self.assertIn("Путин", it)  # "Според Путин": the opener is dropped
        self.assertNotIn("Според Путин", it)
        self.assertNotIn("Министерството", it)  # never inside a sentence -> not a name
        self.assertNotIn("Зеленски", it)  # a single mention at the start of a sentence is no evidence
        tramp = [i for i in M.mine(self.posts(), min_count=3) if i["key"] == M.name_key(["Тръмп"])]
        self.assertEqual(len(tramp), 1)  # Тръмп / Тръмпа share a key

    def test_known_country_stop(self):
        ps = self.posts()
        self.assertNotIn("Путин", {i["phrase"] for i in M.mine(ps, known={M.key_of("Путин")})})
        self.assertNotIn("Путин", {i["phrase"] for i in M.mine(ps, is_country=lambda p: p == "Путин")})
        self.assertNotIn("Путин", {i["phrase"] for i in M.mine(ps, stop={"путин"})})


class Classify(unittest.TestCase):
    ITEMS = [{"key": "n:a", "phrase": "Тръмп", "kind": "name", "posts": 9, "forms": {"Тръмп": 9}, "ex": [1], "ctx": "x"},
             {"key": "d:C-400", "phrase": "С-400", "kind": "designation", "posts": 5, "forms": {"С-400": 5}, "ex": [2], "ctx": "y|z"},
             {"key": "d:S-400", "phrase": "S-400", "kind": "designation", "posts": 3, "forms": {"S-400": 3}, "ex": [3], "ctx": "w"},
             {"key": "n:b", "phrase": "Киев", "kind": "name", "posts": 4, "forms": {"Киев": 4}, "ex": [4], "ctx": "v"},
             {"key": "n:c", "phrase": "Според", "kind": "name", "posts": 3, "forms": {"Според": 3}, "ex": [5], "ctx": "u"}]
    ANS = {"Тръмп": ["person", "Donald Trump"], "С-400": ["weapon", "S-400"], "S-400": ["weapon", "S-400"], "Киев": ["place", ""], "Според": "other"}

    def test_norm(self):
        self.assertEqual(C.norm_answer(["weapon", "S-400"]), ["weapon", "S-400"])
        self.assertEqual(C.norm_answer(["person", ""]), ["other", ""])
        self.assertEqual(C.norm_answer(["banana", "x"]), ["other", ""])
        self.assertEqual(C.norm_answer(None), ["other", ""])
        self.assertEqual(C.norm_answer(["place", "Kyiv"]), ["place", ""])

    def test_run_group_resume(self):
        sent = []
        def call(text):
            sent.append(text)
            return "```json\n" + json.dumps({str(i): self.ANS[l.split("|")[1]] for i, l in enumerate(text.splitlines(), 1)}) + "\n```"
        done, saves = {}, []
        st = C.run(self.ITEMS, done, call, batch=3, sleep=0, save=lambda: saves.append(len(done)))
        self.assertEqual((st, len(sent), saves), ("finished", 2, [3, 5]))
        entries, skipped = C.candidates(self.ITEMS, done)
        ids = {e["id"]: e for e in entries}
        self.assertEqual(set(ids), {"person:donald-trump", "weapon:s-400"})  # С-400 and S-400 merged
        self.assertEqual(ids["weapon:s-400"]["aliases"], ["С-400", "S-400"])
        self.assertEqual(ids["weapon:s-400"]["posts_approx"], 8)
        self.assertEqual(ids["weapon:s-400"]["name_bg"], "С-400")
        self.assertEqual(skipped["place"], ["Киев"])
        self.assertTrue(all(e["keep"] for e in entries))
        self.assertEqual(C.run(self.ITEMS, done, call, batch=3, sleep=0), "finished")
        self.assertEqual(len(sent), 2)  # nothing is asked twice

    def test_failures_stop(self):
        def bad(text): raise extract.LLMError("down")
        self.assertIn("3 failed", C.run(self.ITEMS, {}, bad, batch=1, sleep=0))
        def quota(text): raise extract.QuotaExceeded("limit")
        self.assertIn("quota", C.run(self.ITEMS, {}, quota, batch=1, sleep=0))
        self.assertIn("max-batches", C.run(self.ITEMS, {}, lambda t: '{"1":["other"]}', batch=1, max_batches=1, sleep=0))


class Review(unittest.TestCase):
    def test_prune_aliases(self):
        self.assertEqual(C.prune_aliases(["САЩ Доналд Тръмп", "Доналд Тръмп", "Тръмп Доналд"]), ["Доналд Тръмп", "Тръмп Доналд"])
        self.assertEqual(C.prune_aliases(["НАТО Йенс Столтенберг", "НАТО"]), ["НАТО"])
        self.assertEqual(C.prune_aliases(["Ню Йорк Таймс"]), ["Ню Йорк Таймс"])

    def test_same_word(self):
        self.assertTrue(C.same_word("Зеленския", "Зеленски"))
        self.assertTrue(C.same_word("Тръмпа", "Тръмп"))
        self.assertFalse(C.same_word("Зелената", "Зеленски"))
        self.assertFalse(C.same_word("Зеленов", "Зеленски"))

    def test_strip_glue_and_blacklist(self):
        glue = {"украйна", "кремъл"}
        self.assertEqual(C.strip_glue("САЩ Доналд Тръмп", glue), "Доналд Тръмп")
        self.assertEqual(C.strip_glue("Украйна Володимир Зеленски", glue), "Володимир Зеленски")
        self.assertEqual(C.strip_glue("ООН Антониу Гутериш", glue), "Антониу Гутериш")
        self.assertEqual(C.strip_glue("Башар Асад", glue), "Башар Асад")
        self.assertEqual(C.strip_glue("Сирия Ахмад", {"сирия"}), "Сирия Ахмад")  # only two words: left alone
        items = [{"key": "a", "phrase": "Украйна", "kind": "name", "posts": 50, "forms": {"Украйна": 50}, "ex": [1], "ctx": ""},
                 {"key": "b", "phrase": "Украйна Володимир Зеленски", "kind": "name", "posts": 9, "forms": {"Украйна Володимир Зеленски": 9}, "ex": [2], "ctx": ""},
                 {"key": "c", "phrase": "Медински", "kind": "name", "posts": 5, "forms": {"Медински": 4, "Медина": 1}, "ex": [3], "ctx": ""}]
        done = {"a": ["country", ""], "b": ["person", "Volodymyr Zelensky"], "c": ["person", "Dmitry Medinsky"]}
        ents, _ = C.candidates(items, done)
        al = {e["name_en"]: e["aliases"] for e in ents}
        self.assertEqual(al, {"Volodymyr Zelensky": ["Володимир Зеленски"], "Dmitry Medinsky": ["Медински"]})

    def test_person_shown_with_full_name(self):
        items = [{"key": "a", "phrase": "Тръмп", "kind": "name", "posts": 90, "forms": {"Тръмп": 90}, "ex": [1], "ctx": ""},
                 {"key": "b", "phrase": "Доналд Тръмп", "kind": "name", "posts": 40, "forms": {"Доналд Тръмп": 40}, "ex": [2], "ctx": ""},
                 {"key": "c", "phrase": "Асад", "kind": "name", "posts": 9, "forms": {"Асад": 9}, "ex": [3], "ctx": ""},
                 {"key": "d", "phrase": "Шараа", "kind": "name", "posts": 5, "forms": {"Шараа": 5}, "ex": [4], "ctx": ""}]
        done = {"a": ["person", "Donald Trump"], "b": ["person", "Donald Trump"], "c": ["person", "Bashar al-Assad"], "d": ["person", "Ahmed al-Sharaa"]}
        ents, _ = C.candidates(items, done)
        by = {e["name_en"]: e for e in ents}
        self.assertEqual((by["Donald Trump"]["name_bg"], by["Donald Trump"]["aliases"]), ("Доналд Тръмп", ["Тръмп"]))
        self.assertEqual(by["Bashar al-Assad"]["name_bg"], "Башар Асад")  # from the display table: only the surname was mined
        self.assertEqual(by["Ahmed al-Sharaa"]["name_bg"], "Ахмед ал-Шараа")
        self.assertNotIn("_forms", by["Donald Trump"])

    def test_keep_flags_survive_rebuild(self):
        import tempfile
        d = Path(tempfile.mkdtemp()) / "c.json"
        d.write_text(json.dumps({"entries": [{"id": "person:a", "keep": False}, {"id": "org:b", "keep": True}]}))
        self.assertEqual(C.old_keeps(d), {"person:a": False, "org:b": True})
        self.assertEqual(C.old_keeps(d.with_name("missing.json")), {})

    def test_fix(self):
        items = [{"key": "k1", "phrase": "Ройтерс"}, {"key": "k2", "phrase": "Мерц"}, {"key": "k3", "phrase": "Кац"},
                 {"key": "k4", "phrase": "Али Хаменей"}, {"key": "k5", "phrase": "Тръмп"}]
        done = {"k1": ["org", "Reuters"], "k2": ["person", "Merkel"], "k3": ["person", "Israel Katz"], "k5": ["person", "Donald Trump"]}
        out, _ = F.fix(items, done)
        self.assertEqual(out, {"k1": ["media", ""], "k2": ["person", "Friedrich Merz"], "k4": ["person", "Ali Khamenei"]})


class Promote(unittest.TestCase):
    def test_promote(self):
        cand = {"entries": [
            {"id": "person:a", "type": "person", "name_en": "A", "name_bg": "А", "aliases": ["А", "Ам"], "keep": True},
            {"id": "person:b", "type": "person", "name_en": "B", "aliases": ["Б"], "keep": False},
            {"id": "org:iran", "type": "org", "name_en": "Iran", "aliases": ["Иран"], "keep": True}]}
        dic = {"entities": [{"id": "person:a", "type": "person", "name_en": "A", "name_bg": "А", "aliases": ["А"], "patterns": []}]}
        new, added, ext, sk = P.promote(cand, dic, {"iran"})
        self.assertEqual((added, ext, sk), ([], ["person:a"], ["org:iran"]))
        self.assertEqual(new["entities"][0]["aliases"], ["А", "Ам"])
        base = {"entities": [{"id": "person:x", "type": "person", "name_en": "X", "name_bg": "Х", "aliases": ["Х"], "patterns": []}]}
        new, added, ext, sk = P.promote({"entries": []}, base, (), [{"type": "person", "name_en": "X", "aliases": [], "not_after": ["Рифат"]}])
        self.assertEqual((ext, new["entities"][0]["not_after"]), (["person:x"], ["Рифат"]))
        new, added, ext, sk = P.promote({"entries": []}, {"entities": []}, (), [{"type": "org", "name_en": "Houthis", "aliases": ["хуситите", "Ансар Аллах"]}])
        self.assertEqual(added, ["org:houthis"])
        self.assertEqual(new["entities"][0]["name_bg"], "хуситите")


class AskCompat(unittest.TestCase):
    def test_default_body_unchanged_and_new_options(self):
        seen = []
        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                out = json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
            def log_message(self, *a): pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_port}"
        extract.ask("x" * 2000, "m", "k", url)
        extract.ask("y" * 2000, "m", "k", url, system="S", max_tokens=5, max_text=10, extra={"reasoning_effort": "low"})
        srv.shutdown()
        a, b = seen
        self.assertEqual((a["max_tokens"], len(a["messages"][1]["content"]), a["messages"][0]["content"] == extract.SYSTEM), (2000, min(2000, extract.MAX_TEXT), True))  # the text sent is 2000 chars; MAX_TEXT is only the cap
        self.assertEqual(set(a), {"model", "temperature", "max_tokens", "messages"})
        self.assertEqual((b["max_tokens"], b["messages"][0]["content"], len(b["messages"][1]["content"]), b["reasoning_effort"]), (5, "S", 10, "low"))


if __name__ == "__main__":
    unittest.main()
