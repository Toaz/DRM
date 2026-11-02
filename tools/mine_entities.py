"""Mine recurring names and weapon designations from every post (free: no LLM, no network).

  python tools/mine_entities.py                    # all posts -> data/entity_mined.json
  python tools/mine_entities.py --min 5 --top 800
  python tools/mine_entities.py --since 2025-01-01

Lists capitalised phrases of 1-4 words found in at least --min posts (a single word counts only when it stands inside
a sentence, so a sentence-opening "Министерството" is not a name) and digit designations such as F-16, С-400, Ми-8.
Bulgarian endings are folded (Тръмп / Тръмпа -> one item). Left out: countries (via place.CRX), phrases already in
data/entities.json, and phrases listed in data/entity_stop.txt (one per line, optional).
Run it again once the dictionary exists to see what is still missing.
"""
import sys, re, json, argparse, collections, datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from common import DATA, load_all, txt

OUT = DATA / "entity_mined.json"
DICT = DATA / "entities.json"
STOPFILE = DATA / "entity_stop.txt"
STOP = {"telegram", "срочно", "извънредно", "важно", "видео", "снимка", "снимки", "източник", "източници", "update",
        "breaking", "live", "covid", "реклама", "абонирай", "абонирайте"}

L = "A-Za-zА-Яа-яЁё0-9_"
UP, LO = "A-ZА-ЯЁ", "a-zа-яё"
WORD = rf"(?:[{UP}][{LO}]+(?:-[{UP}]?[{LO}]+)*|[{UP}]{{2,5}}(?![{UP}{LO}0-9]))"
TOK = re.compile(WORD)
RUN = re.compile(rf"(?<![{L}\-]){WORD}(?:[ \u00a0]{WORD}){{0,3}}")
DES = re.compile(rf"(?<![{L}\-])([{UP}][A-Za-zА-Яа-яЁё]{{0,3}})-([{UP}]{{0,2}}\d{{1,4}}[A-Za-zА-Яа-яЁё0-9]{{0,3}})(?![{L}])")
JUNK = re.compile(r"https?://\S+|t\.me/\S+|@\w+|#\w+")
FOLD = str.maketrans("АВЕКМНОРСТХУ", "ABEKMHOPCTXY")  # Cyrillic look-alikes -> Latin, so С-400 and C-400 merge
SUF = sorted("ският ския ската ското ските ски ска ско ият ите ата ото ето ия ят ът ов ев а я у ю е и".split(), key=len, reverse=True)


def stem(w):
    """Crude Bulgarian ending removal, used only to group variants of one name (not to match text)."""
    lw = w.lower()
    if not re.search("[а-яё]", lw) or (w.isupper() and len(w) <= 5):
        return lw
    for _ in range(3):
        for s in SUF:
            if lw.endswith(s) and len(lw) - len(s) >= 4:
                lw = lw[:-len(s)]
                break
        else:
            break
    return lw


def name_key(toks):
    return "n:" + " ".join(stem(t) for t in toks)


def des_key(surface):
    return "d:" + surface.upper().translate(FOLD)


def key_of(s):
    """Key of a dictionary string (name or designation), or None."""
    s = s.strip()
    if DES.fullmatch(s):
        return des_key(s)
    toks = TOK.findall(s)
    return name_key(toks) if toks else None


def is_initial(text, start):
    """True if the word stands at the start of a sentence, line or bullet (so a capital letter proves nothing)."""
    prev = text[max(0, start - 8):start].rstrip(" \t\u00a0«\"„“(['")
    return not prev or prev[-1] in ".!?…:\n\r" or not (prev[-1].isalnum() or prev[-1] in ",;)»”\"'")


def scan(text):
    """-> (designations [(start, end, surface)], runs [(start, end, tokens, initial)]) with offsets in `text`."""
    des = [(m.start(), m.end(), m.group()) for m in DES.finditer(text)]
    blank = DES.sub(lambda m: " " * len(m.group()), text)  # same length, so offsets stay valid
    runs = [(m.start(), m.end(), TOK.findall(m.group()), is_initial(blank, m.start())) for m in RUN.finditer(blank)]
    return des, runs


def mine(posts, min_count=3, top=1200, ctx=60, known=(), is_country=None, stop=()):
    """Count phrases over `posts` (dicts with id/text). Returns a list of items, most frequent first."""
    docs = []
    for m in posts:
        t = JUNK.sub(lambda x: " " * len(x.group()), txt(m))
        if len(t.strip()) > 20:
            docs.append((m["id"], t) + scan(t))
    ini, mid = collections.Counter(), collections.Counter()
    for _, _, _, runs in docs:
        for _, _, toks, first in runs:
            for i, tk in enumerate(toks):
                (ini if (i == 0 and first) else mid)[tk] += 1
    starters = {w for w, n in ini.items() if n + mid[w] >= 15 and mid[w] < 0.1 * (n + mid[w])}  # "Според", "Министерството"
    agg = {}

    def add(key, phrase, kind, pid, mid_occ, t, s, e):
        a = agg.setdefault(key, {"kind": kind, "forms": collections.Counter(), "ids": [], "initial": 0, "ctx": ""})
        if not mid_occ:
            a["initial"] += 1
            return
        a["forms"][phrase] += 1
        if not a["ids"] or a["ids"][-1] != pid:
            a["ids"].append(pid)
        if not a["ctx"]:
            a["ctx"] = " ".join(t[max(0, s - ctx // 2):e + ctx // 2].split())

    for pid, t, des, runs in docs:
        for s, e, surface in des:
            add(des_key(surface), surface, "designation", pid, True, t, s, e)
        for s, e, toks, first in runs:
            dropped = 0
            while first and toks and toks[0] in starters:
                toks, dropped = toks[1:], dropped + 1
            if toks:
                add(name_key(toks), " ".join(toks), "name", pid, (not first) or dropped > 0 or len(toks) > 1, t, s, e)
    items = []
    for key, a in agg.items():
        ids = sorted(set(a["ids"]))
        if len(ids) < min_count or key in known:
            continue
        forms = a["forms"].most_common(8)
        best = forms[0][0]
        if best.lower() in STOP or best.lower() in stop or key[2:] in stop:
            continue
        if is_country and any(is_country(f) for f, _ in forms[:3]):
            continue
        items.append({"key": key, "phrase": best, "kind": a["kind"], "posts": len(ids), "initial": a["initial"],
                      "forms": dict(forms), "ex": ids[-3:], "ctx": a["ctx"]})
    items.sort(key=lambda x: (-x["posts"], x["phrase"]))
    return items[:top]


def country_filter():
    """Predicate 'is this phrase a country name' built from place.CRX; harmless no-op if that fails."""
    rx = []
    try:
        import place
        crx = place.CRX
        for v in (crx.values() if isinstance(crx, dict) else crx):
            if isinstance(v, (tuple, list)):
                v = next((x for x in reversed(v) if isinstance(x, (str, re.Pattern))), None)
            v = v.pattern if isinstance(v, re.Pattern) else v
            try:
                rx.append(re.compile(v, re.I))
            except (re.error, TypeError):
                pass
    except Exception as e:
        print("country filter off:", e)
    print(f"country filter: {len(rx)} patterns")

    def f(p):
        for r in rx:
            m = r.search(p)
            if m and m.start() == 0 and m.end() >= len(p) - 3:
                return True
        return False
    return f


def known_keys(path=DICT):
    keys = set()
    if path.exists():
        for e in json.load(open(path, encoding="utf-8")).get("entities", []):
            for s in [e.get("name_en"), e.get("name_bg"), *e.get("aliases", [])]:
                k = key_of(s) if s else None
                if k:
                    keys.add(k)
    return keys


def write(items, path, meta):
    lines = ",\n".join(json.dumps(i, ensure_ascii=False) for i in items)
    path.write_text('{"version":1,"meta":%s,"items":[\n%s\n]}\n' % (json.dumps(meta, ensure_ascii=False), lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min", type=int, default=3, help="minimum number of posts (default 3)")
    ap.add_argument("--top", type=int, default=1200, help="keep this many items (default 1200)")
    ap.add_argument("--since", default="", help="ignore posts older than YYYY-MM-DD")
    ap.add_argument("--no-countries", action="store_true", help="do not filter country names")
    a = ap.parse_args()
    posts = [m for m in load_all() if m.get("date", "")[:10] >= a.since]
    stop = {l.strip().lower() for l in STOPFILE.read_text(encoding="utf-8").splitlines() if l.strip()} if STOPFILE.exists() else set()
    known = known_keys()
    items = mine(posts, a.min, a.top, known=known, is_country=None if a.no_countries else country_filter(), stop=stop)
    meta = {"posts": len(posts), "min": a.min, "top": a.top, "since": a.since, "in_dictionary": len(known),
            "date": dt.date.today().isoformat()}
    write(items, OUT, meta)
    nm = [i for i in items if i["kind"] == "name"]
    ds = [i for i in items if i["kind"] == "designation"]
    print(f"{len(posts)} posts -> {len(nm)} names, {len(ds)} designations -> {OUT}")
    print("top names:", ", ".join(f"{i['phrase']} ({i['posts']})" for i in nm[:25]))
    print("top designations:", ", ".join(f"{i['phrase']} ({i['posts']})" for i in ds[:15]))


if __name__ == "__main__":
    main()
