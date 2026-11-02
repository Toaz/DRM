"""One-off: let the LLM classify the phrases found by tools/mine_entities.py. Never edits data/entities.json.

  export GROQ_API_KEY=...                           # key from the environment only, never written to a file
  python tools/classify_entities.py --dry           # how many requests, nothing is sent
  python tools/classify_entities.py                 # classify everything not done yet (default 60 phrases per request)
  python tools/classify_entities.py --batch 100 --max-batches 3
  python tools/classify_entities.py --rebuild       # only regroup the saved answers (no API call)

Reads  data/entity_mined.json        (from mine_entities.py)
Keeps  data/entity_classified.json   (raw answers per phrase; a stopped or failed run continues where it ended)
Writes data/entities_candidates.json (grouped person / org / unit / weapon entries with "keep": true, for you to review;
                                      places, countries and "other" are listed under "skipped")
Next:  edit the candidates (set "keep": false, fix names), then python tools/promote_entities.py
"""
import sys, os, re, json, time, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import extract
from common import DATA
from fix_entities import DROP_ALIASES, DISPLAY_BG

MINED = DATA / "entity_mined.json"
DONE = DATA / "entity_classified.json"
OUT = DATA / "entities_candidates.json"
TYPES = ("person", "org", "unit", "weapon")
SKIP = ("place", "country", "media", "other")

SYSTEM = """You classify phrases mined from a Bulgarian military and geopolitics news channel.
Each input line is: n|phrase|context. The phrase may be an inflected Bulgarian form or a Cyrillic spelling of a foreign name.
Answer with ONE JSON object and nothing else: {"1": [type, english_name], "2": [type, english_name], ...} for every n.
type is exactly one of:
person  - a named human (Putin, Netanyahu, Gerasimov)
org     - government body, ministry, agency, armed group or militia, party, company, alliance, media outlet (Hezbollah, Pentagon, NATO, Wagner)
unit    - a specific military formation, unit or named ship (47th Mechanized Brigade, Azov, Black Sea Fleet, Moskva)
weapon  - a named weapon system, aircraft, missile, drone, vehicle or ship class, or a designation like F-16, S-400, Su-35 (Patriot, Shahed, Iskander)
place   - city, region, strait, base, building (not a country)
country - a country, its demonym, or the blocs EU and UN
media   - news agency, newspaper, TV channel, website, social network or messenger (Reuters, CNN, Telegram)
other   - generic word, title, month, sentence opener, abbreviation you cannot resolve, or anything you are not sure about
english_name: the usual English name or designation ("Donald Trump", "Shahed", "S-400", "Su-35"); Cyrillic and Latin spellings of one
designation give the same name. Use "" for place, country and other. Use the context to resolve ambiguity. Never guess: unsure means other."""


def norm_answer(v):
    """One model answer -> [type, name]; anything odd becomes ["other", ""]."""
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, (list, tuple)) or not v:
        return ["other", ""]
    t = str(v[0]).strip().lower()
    name = str(v[1]).strip()[:60] if len(v) > 1 and v[1] else ""
    if t not in TYPES + SKIP or (t in TYPES and not name):
        return ["other", ""]
    return [t, name if t in TYPES else ""]


def classify_batch(batch, call):
    """batch: mined items. call(user_text) -> raw model text. Returns {key: [type, name]}; missing answers are left out."""
    lines = "\n".join(f"{i}|{it['phrase']}|{it['ctx'].replace('|', '/')}" for i, it in enumerate(batch, 1))
    ans = extract.parse(call(lines))
    return {it["key"]: norm_answer(ans[str(i)]) for i, it in enumerate(batch, 1) if str(i) in ans}


def slug(name):
    return re.sub(r"[\W_]+", "-", name.lower()).strip("-")


def candidates(items, done):
    """Group classified items by (type, English name): Cyrillic and Latin spellings of one thing become one entry."""
    groups, skipped = {}, {s: [] for s in SKIP}
    glue = {it["phrase"].lower() for it in items if " " not in it["phrase"] and done.get(it["key"], [""])[0] in ("country", "place", "org", "unit", "media")}
    for it in items:
        t, name = done.get(it["key"], [None, ""])
        if t in SKIP:
            skipped[t].append(it["phrase"])
        elif t in TYPES and slug(name):
            g = groups.setdefault((t, name.casefold()), {"id": f"{t}:{slug(name)}", "type": t, "name_en": name, "name_bg": "",
                                                          "aliases": [], "posts_approx": 0, "ex": [], "keep": True, "_forms": []})
            g["name_bg"] = g["name_bg"] or it["phrase"]  # items arrive most frequent first
            g["posts_approx"] += it["posts"]  # a sum: a post mentioning two spellings is counted twice
            for f in it["forms"]:
                if not same_word(f, it["phrase"]):
                    continue
                f = strip_glue(f, glue) if t == "person" else f
                if f not in g["aliases"] and f.lower() not in DROP_ALIASES:
                    g["aliases"].append(f)
                    g["_forms"].append(f)
            g["ex"] = (g["ex"] + [i for i in it["ex"] if i not in g["ex"]])[:3]
    entries = sorted(groups.values(), key=lambda g: -g["posts_approx"])
    for g in entries:
        forms = g.pop("_forms")
        if forms:  # a person is shown with the full name: most words first, then the most frequent form
            best = max(forms, key=lambda f: (len(f.split()), -forms.index(f))) if g["type"] == "person" else forms[0]
            if g["type"] == "person" and len(best.split()) < 2 and g["name_en"] in DISPLAY_BG:
                best = DISPLAY_BG[g["name_en"]]
            g["name_bg"] = best
        g["aliases"] = prune_aliases(g["aliases"])
    entries = [g for g in entries if g["aliases"]]
    return entries, skipped


def prune_aliases(aliases):
    """Drop an alias that starts or ends with another alias of the same entry ("САЩ Доналд Тръмп" next to "Доналд Тръмп"):
    the shorter one already matches, and the longer one often glues in a second entity ("НАТО Йенс Столтенберг")."""
    toks = [a.lower().split() for a in aliases]
    return [a for i, a in enumerate(aliases)
            if not any(j != i and 0 < len(b) < len(toks[i]) and (toks[i][:len(b)] == b or toks[i][-len(b):] == b) for j, b in enumerate(toks))]


def same_word(f, best):
    """Stemming can lump unrelated words under one key ("Зеленски" with "Зелената"): keep a form only if it starts like the main form."""
    f, best = f.lower(), best.lower()
    n = 0
    while n < min(len(f), len(best)) and f[n] == best[n]:
        n += 1
    return n >= min(len(best), max(4, len(best) - 2))


def strip_glue(alias, glue):
    """"САЩ Доналд Тръмп" -> "Доналд Тръмп": drop a leading country, organisation or acronym that is stuck to a person's name.
    glue = lower-case single-word phrases that were classified as country / place / org / unit / media."""
    t = alias.split()
    while len(t) >= 3 and (t[0].lower() in glue or (t[0].isupper() and len(t[0]) <= 5)):
        t = t[1:]
    return " ".join(t)


def old_keeps(path=None):
    """The "keep" flags you set in an earlier candidates file, so that a rebuild never loses your review."""
    try:
        return {e["id"]: e["keep"] for e in json.load(open(path or OUT, encoding="utf-8"))["entries"]}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def save_json(path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def write_candidates(items, done, meta):
    entries, skipped = candidates(items, done)
    keeps = old_keeps()
    for e in entries:
        e["keep"] = keeps.get(e["id"], True)
    lines = ",\n".join(json.dumps(e, ensure_ascii=False) for e in entries)
    OUT.write_text('{"version":1,"meta":%s,\n"skipped":%s,\n"entries":[\n%s\n]}\n' % (
        json.dumps(meta, ensure_ascii=False), json.dumps(skipped, ensure_ascii=False), lines), encoding="utf-8")
    return entries, skipped


def run(items, done, call, batch=60, max_batches=0, sleep=2.0, save=None):
    """Classify the items that have no answer yet. Stops on quota or after 3 failed batches in a row. Returns a status string."""
    todo = [it for it in items if it["key"] not in done]
    fails = n = 0
    for i in range(0, len(todo), batch):
        if max_batches and n >= max_batches:
            return "stopped at --max-batches"
        part = todo[i:i + batch]
        try:
            got = classify_batch(part, call)
            fails = 0
        except extract.QuotaExceeded as e:
            return f"quota reached, run again later ({e})"
        except (extract.LLMError, ValueError) as e:
            fails += 1
            print("batch failed:", str(e)[:200])
            if fails >= 3:
                return "3 failed batches in a row, stopped"
            continue
        done.update(got)
        n += 1
        print(f"batch {n}: {len(got)}/{len(part)} answers, {len(todo) - i - len(part)} phrases left")
        if save:
            save()
        time.sleep(sleep)
    return "finished"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", type=int, default=60, help="phrases per request (default 60; lower if you hit token limits)")
    ap.add_argument("--max-batches", type=int, default=0, help="stop after this many requests (0 = no limit)")
    ap.add_argument("--sleep", type=float, default=2.0, help="seconds between requests")
    ap.add_argument("--dry", action="store_true", help="count only, send nothing, write nothing")
    ap.add_argument("--rebuild", action="store_true", help="regroup saved answers into the candidates file, no API call")
    a = ap.parse_args()
    if not MINED.exists():
        sys.exit("data/entity_mined.json not found: run tools/mine_entities.py first")
    items = json.load(open(MINED, encoding="utf-8"))["items"]
    saved = json.load(open(DONE, encoding="utf-8")) if DONE.exists() else {"version": 1, "model": "", "done": {}}
    done = saved["done"]
    todo = [it for it in items if it["key"] not in done]
    reqs = -(-len(todo) // a.batch)
    chars = sum(len(it["phrase"]) + len(it["ctx"]) + 6 for it in todo)
    print(f"{len(items)} mined phrases, {len(done)} already classified, {len(todo)} to do = {reqs} requests, ~{chars // 2 + reqs * 450} input tokens")
    if a.dry:
        return
    status = "rebuild only"
    if todo and not a.rebuild:
        provider = os.environ.get("LLM_PROVIDER", "groq")
        if provider not in extract.PROVIDERS:
            sys.exit(f"LLM_PROVIDER must be one of {', '.join(extract.PROVIDERS)}")
        base_url, env, default_model = extract.PROVIDERS[provider]
        model = os.environ.get("LLM_MODEL") or default_model
        token = os.environ.get(env)
        if not token or not model:
            sys.exit(f"No {env if not token else 'LLM_MODEL'} set. Nothing sent.")
        saved["model"] = f"{provider}/{model}"
        extra = {"reasoning_effort": "low"} if "gpt-oss" in model else None  # fewer hidden tokens for a simple task
        call = lambda t: extract.ask(t, model, token, base_url, system=SYSTEM, max_tokens=6000, max_text=60000, extra=extra)
        status = run(items, done, call, a.batch, a.max_batches, a.sleep, save=lambda: save_json(DONE, saved))
        save_json(DONE, saved)
    meta = {"model": saved.get("model", ""), "classified": len(done), "of": len(items), "mined_posts": json.load(open(MINED, encoding="utf-8"))["meta"].get("posts")}
    entries, skipped = write_candidates(items, done, meta)
    by = {t: sum(1 for e in entries if e["type"] == t) for t in TYPES}
    print(f"{status}. {len(entries)} candidates {by}; skipped " + ", ".join(f"{k} {len(v)}" for k, v in skipped.items()) + f" -> {OUT}")


if __name__ == "__main__":
    main()
