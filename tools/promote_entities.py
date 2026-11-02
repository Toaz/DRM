"""Merge the reviewed candidates into the dictionary data/entities.json (the only script that writes it).

  python tools/promote_entities.py --dry     # show what would change
  python tools/promote_entities.py           # add entries with "keep": true; existing ids only get new aliases

Review data/entities_candidates.json first (set "keep": false, fix name_en / name_bg / aliases). `patterns` is for optional
hand-written regexes; the G2 matcher builds its patterns from name_en, name_bg and aliases when it is empty.
data/entities_manual.json (optional, hand-written: {"entities": [{"type", "name_en", "aliases"}]}) is added too:
use it for names the miner cannot see, such as lowercase ones (хуситите). Entries whose English name is a country are skipped (countries stay in the country layer). Review the git diff afterwards.
"""
import sys, re, json, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from common import DATA

CAND, DICT, MANUAL = DATA / "entities_candidates.json", DATA / "entities.json", DATA / "entities_manual.json"
TYPES = ("person", "org", "unit", "weapon")


def country_names():
    try:
        import pycountry
        return {n.casefold() for c in pycountry.countries for n in (c.name, getattr(c, "common_name", ""), getattr(c, "official_name", "")) if n}
    except ImportError:
        return set()


def promote(cand, dic, countries=(), manual=()):
    """Returns (new dictionary dict, added ids, extended ids, skipped ids). `manual`: hand-written entries
    (type, name_en, aliases; optional name_bg / patterns), always included."""
    ents = {e["id"]: e for e in dic.get("entities", [])}
    added, extended, skipped = [], [], []
    mine = [dict(m, id=f"{m['type']}:{re.sub(r'[\W_]+', '-', m['name_en'].lower()).strip('-')}", keep=True) for m in manual]
    for c in cand.get("entries", []) + mine:
        if not c.get("keep") or c.get("type") not in TYPES or not c.get("name_en"):
            continue
        if c["name_en"].casefold() in countries:
            skipped.append(c["id"])
            continue
        e = ents.get(c["id"])
        if e is not None and c.get("not_after") and not set(c["not_after"]) <= set(e.get("not_after", [])):
            e["not_after"] = sorted(set(e.get("not_after", [])) | set(c["not_after"]))
            extended.append(c["id"])
        if e is None:
            ents[c["id"]] = {"id": c["id"], "type": c["type"], "name_en": c["name_en"],
                             "name_bg": c.get("name_bg") or (c.get("aliases") or [""])[0],
                             "aliases": list(dict.fromkeys(c.get("aliases", []))), "patterns": list(c.get("patterns", []))}
            if c.get("not_after"):
                ents[c["id"]]["not_after"] = sorted(set(c["not_after"]))
            added.append(c["id"])
        else:
            new = [a for a in c.get("aliases", []) if a not in e["aliases"]]
            if new:
                e["aliases"] += new
                extended.append(c["id"])
    return {"version": 1, "entities": list(ents.values())}, added, extended, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    if not CAND.exists():
        sys.exit("data/entities_candidates.json not found: run tools/classify_entities.py first")
    dic = json.load(open(DICT, encoding="utf-8")) if DICT.exists() else {"version": 1, "entities": []}
    manual = json.load(open(MANUAL, encoding="utf-8")).get("entities", []) if MANUAL.exists() else []
    new, added, extended, skipped = promote(json.load(open(CAND, encoding="utf-8")), dic, country_names(), manual)
    print(f"{len(added)} added, {len(extended)} got new aliases, {len(skipped)} skipped as countries, {len(new['entities'])} in total")
    if a.dry:
        return
    lines = ",\n".join(json.dumps(e, ensure_ascii=False) for e in new["entities"])
    DICT.write_text('{"version":1,"entities":[\n%s\n]}\n' % lines, encoding="utf-8")
    print("written", DICT)


if __name__ == "__main__":
    main()
