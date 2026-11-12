"""events.json (+ curated.json) -> data/graph/nodes.json, edges.json, summary.json, site/graph.html
Run:  python src/graph.py [--events data/events.json] [--out data/graph] [--html site/graph.html]
Reads JSON lines (one post per line) or a JSON list. Field names are looked up in ALIASES,
so adjust that table if your events.json uses different keys.
"""
import argparse, json, os, sys, collections, glob, re, base64, gzip

ALIASES = {
    "id":        ["id", "post_id", "msg_id"],
    "date":      ["date", "time", "datetime", "ts"],
    "text":      ["text", "snippet", "body"],
    "countries": ["c", "countries", "mentioned", "mentions"],
    "location":  ["loc", "location", "where", "loc_country", "place_country"],
    "place":     ["place", "place_name", "exact_place"],
    "category":  ["cat", "category"],
    "arrows":    ["ev", "arrows", "links", "relations"],
}
ARROW_ALIASES = {
    "src":  ["from", "attacker", "src", "source"],
    "dst":  ["to", "victim", "dst", "target"],
    "conf": ["conf", "confidence", "score"],
    "kind": ["kind", "type"],
    "why":  ["why", "reason"],
}
VERBAL = {"verbal", "threat", "statement", "words"}
CHANNEL = "drmjournal"

def pick(d, key, aliases=ALIASES):
    for k in aliases[key]:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None

def load(path):
    if not os.path.exists(path):
        return []
    raw = open(path, encoding="utf-8").read().strip()
    if not raw:
        return []
    if raw[0] == "[":
        return json.loads(raw)
    if raw[0] == "{":
        try:
            obj = json.loads(raw)
            if isinstance(obj.get("posts"), dict):
                return [{"id": k, **v} for k, v in obj["posts"].items()]
        except json.JSONDecodeError:
            pass   # maybe JSON lines, fall through
    rows = []
    for n, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if line:
            try: rows.append(json.loads(line))
            except json.JSONDecodeError: print(f"skip bad line {n}", file=sys.stderr)
    return rows

def load_meta(data_dir):
    """date + text per post id from data/result_old.json and result_DD.MM.YYYY.json (newest file wins).
    Format guessed: a list of posts, or {"messages": [...]}, each with id, date, text."""
    import glob, re
    def key(p):
        m = re.search(r"result_(\d\d)\.(\d\d)\.(\d{4})", p)
        return (m.group(3), m.group(2), m.group(1)) if m else ("0000", "", "")
    meta = {}
    for p in sorted(glob.glob(os.path.join(data_dir, "result_*.json")), key=key):
        try: obj = json.load(open(p, encoding="utf-8"))
        except Exception as e: print(f"cannot read {p}: {e}", file=sys.stderr); continue
        items = obj if isinstance(obj, list) else (obj.get("messages") or obj.get("posts") or [])
        if isinstance(items, dict): items = [{"id": k, **v} for k, v in items.items()]
        for m in items:
            if not isinstance(m, dict) or m.get("id") is None: continue
            t = m.get("text", "")
            if isinstance(t, list):   # Telegram export: list of strings / {"text":..}
                t = "".join(x if isinstance(x, str) else x.get("text", "") for x in t)
            meta[str(m["id"])] = {"date": m.get("date") or m.get("time") or "", "text": t}
    return meta

CAT_NAMES = {"war": "War", "sea": "Sea", "dip": "Diplomacy", "gen": "General", "avi": "Aviation", "sec": "Security", "cyb": "Cyber"}

def norm_arrow(a):
    if isinstance(a, (list, tuple)):          # tolerate positional arrows
        a = dict(zip(["from", "to", "conf", "kind"], a))
    src, dst = pick(a, "src", ARROW_ALIASES), pick(a, "dst", ARROW_ALIASES)
    if not src or not dst or src == dst:   # no victim country (e.g. "to": null): no ATTACKED edge
        return None
    conf = pick(a, "conf", ARROW_ALIASES)
    kind = str(pick(a, "kind", ARROW_ALIASES) or "physical").lower()
    return (str(src).upper(), str(dst).upper(), float(conf) if conf is not None else 1.0, kind,
            str(pick(a, "why", ARROW_ALIASES) or ""))

DEFAULT_KEYWORDS = {   # fixed list: edit data/keywords.json to change it (substring match, lowercase)
    "drones": ["drone", "uav", "дрон"], "missiles": ["missile", "ракет"], "sanctions": ["sanction", "санкци"],
    "naval": ["tanker", "vessel", "warship", "танкер", "кораб"], "nuclear": ["nuclear", "ядрен"],
    "cyber": ["cyber", "кибер"], "air defence": ["air defen", "patriot", "противовъздуш"]}

def load_keywords(path):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else DEFAULT_KEYWORDS

def make_events(nodes, edges):
    """One flat row per attack/threat: what the web page draws and what its evidence panel lists."""
    post = {n["id"]: n for n in nodes if n["type"] == "post"}
    lab = {n["id"]: n["label"] for n in nodes}
    kw, cat = collections.defaultdict(list), {}
    for e in edges:
        if e["type"] == "MENTIONS_KEYWORD": kw[e["source"]].append(lab[e["target"]])
        elif e["type"] == "HAS_CATEGORY": cat[e["source"]] = lab[e["target"]]
    return [{"p": post[e["post"]]["id"][5:], "d": post[e["post"]]["date"], "u": post[e["post"]]["url"],
             "s": e["source"][8:], "t": e["target"][8:], "k": "A" if e["type"] == "ATTACKED" else "T",
             "c": e["confidence"], "w": e.get("why", ""), "x": post[e["post"]]["snippet"],
             "cat": cat.get(e["post"], ""), "kw": kw.get(e["post"], [])}
            for e in edges if e["type"] in ("ATTACKED", "THREATENED")]

def build(rows, curated=None, names=None, meta=None, keywords=None):
    names = names or {}
    meta = meta or {}
    nodes, edges = {}, []
    def node(i, t, label=None, **kw):
        if i not in nodes:
            nodes[i] = {"id": i, "type": t, "label": label or i.split(":", 1)[1], **kw}
        return i
    def country(c):
        c = str(c).upper()
        return node(f"country:{c}", "country", names.get(c, c))

    by_id = {}
    for r in rows:
        pid = pick(r, "id")
        if pid is not None:
            by_id[str(pid)] = r              # later line wins (edited posts)
    for pid, ov in (curated or {}).items():  # curated wins over LLM
        by_id[str(pid)] = {**by_id.get(str(pid), {}), **ov}

    for pid, r in by_id.items():
        m = meta.get(pid, {})
        date = str(pick(r, "date") or m.get("date") or "")[:10]
        full = str(pick(r, "text") or m.get("text") or "")
        text = full[:360]
        p = node(f"post:{pid}", "post", f"#{pid}", date=date,
                 url=f"https://t.me/{CHANNEL}/{pid}", snippet=text)
        for k, al in (keywords or {}).items():
            if any(x in full.lower() for x in al):
                edges.append({"source": p, "target": node(f"keyword:{k}", "keyword", k), "type": "MENTIONS_KEYWORD", "post": p, "date": date})
        cat = pick(r, "category")
        cat_id = node(f"category:{str(cat).lower()}", "category", CAT_NAMES.get(str(cat).lower(), str(cat))) if cat else None
        for c in pick(r, "countries") or []:
            edges.append({"source": p, "target": country(c), "type": "MENTIONS", "post": p, "date": date})
        loc = pick(r, "location")
        if loc:
            edges.append({"source": p, "target": country(loc), "type": "LOCATED_IN", "post": p, "date": date})
        place = pick(r, "place")
        if place:
            pl = node("place:" + str(place).lower().replace(" ", "_"), "place", str(place))
            edges.append({"source": p, "target": pl, "type": "LOCATED_AT", "post": p, "date": date})
        if cat_id:
            edges.append({"source": p, "target": cat_id, "type": "HAS_CATEGORY", "post": p, "date": date})
        for a in pick(r, "arrows") or []:
            na = norm_arrow(a)
            if not na: continue
            s, d, conf, kind, why = na
            etype = "THREATENED" if kind in VERBAL else "ATTACKED"
            edges.append({"source": country(s), "target": country(d), "type": etype, "post": p,
                          "date": date, "confidence": round(conf, 2),
                          "category": cat_id, "why": why})
    return list(nodes.values()), edges

def summarize(edges):
    """Aggregate repeated pairs into one weighted line."""
    agg = collections.defaultdict(lambda: {"count": 0, "conf_sum": 0.0, "first": "9999", "last": "", "posts": [], "why": []})
    for e in edges:
        if e["type"] in ("ATTACKED", "THREATENED"):
            a = agg[(e["source"], e["target"], e["type"])]
            a["count"] += 1; a["conf_sum"] += e["confidence"]
            a["first"] = min(a["first"], e["date"] or "9999"); a["last"] = max(a["last"], e["date"])
            a["posts"].append(e["post"])
            if e.get("why") and len(a["why"]) < 5: a["why"].append(e["why"])
    out = [{"source": s, "target": t, "type": ty, "count": a["count"],
            "avg_confidence": round(a["conf_sum"] / a["count"], 2),
            "first": a["first"], "last": a["last"], "posts": a["posts"], "why": a["why"]}
           for (s, t, ty), a in agg.items()]
    return sorted(out, key=lambda x: -x["count"])

# ---------------------------------------------------------------------------------------------------------------------
# Page data: the graph page (country arrows + people/organisations/units/weapons) is computed from what the MAP shows.
# One compact record per post goes into the page; the page counts, filters and applies the hand edits on its own.
# ---------------------------------------------------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNIP, PAGE_LIMIT = 140, 10_000_000    # characters of text shown per post, page size that triggers shorter texts and, last, no text search
TH_NAMES = {"ua": "Руско-украинска война", "me": "Близкият изток", "eu": "Европа и Черно море", "as": "Азия и Тихия океан", "am": "Америка", "af": "Африка",
            "ru": "Русия: вътрешни и чума (ръчно)", "gl": "Глобално / друго"}           # copied from the map page (TH); keep in sync with template/template.html
CT_NAMES = {"war": "Удар или атака", "mil": "Военно придвижване", "dip": "Дипломация и политика", "sea": "Море и кораби", "eng": "Енергетика и икономика",
            "hum": "Хуманитарни и здраве", "sec": "Сигурност и разузнаване", "nuc": "Ядрени и стратегически", "air": "ПВО и ракети", "cyb": "Кибер и информация",
            "ter": "Тероризъм и заложници", "pro": "Протести и размирици", "dis": "Бедствия и инциденти", "arm": "Въоръжение и техника",
            "avi": "Авиация и въздушно пространство", "gen": "Общо съобщение"}           # the map's CT
FT_CHARS = 1500                                  # characters of every post kept for the text search
CLS = {"curated": "c", "hand": "c", "llm": "l"}   # where an arrow comes from: c = checked by hand, l = model, r = keyword rules (weakest)


def row_arrows(r, src):
    """Arrows of one map row (build.make_rows format): [(from ISO, to ISO, 'A' attack | 'T' threat, class)].
    Row column 8 holds the drawn arrows (kind 'p'/'v' at index 5), column 13 the country pair of each: [from, to] with '' = the place named in the post, '?' = not known."""
    pairs = r[13] if len(r) > 13 and r[13] else []
    drawn = r[8] or []
    out = []
    for j, p in enumerate(pairs):
        a, b = (p + ["", ""])[:2]
        if not a or not b or b == "?" or a == b:
            continue
        kind = drawn[j][5] if j < len(drawn) and drawn[j] and len(drawn[j]) > 5 else "p"
        x = (a, b, "T" if kind == "v" else "A", CLS.get(src, "r"))
        if x not in out:
            out.append(x)
    return out


# ---- countries mentioned in a post: flags at the start (strongest), flags elsewhere, names of countries in the text
FLAG_RX = re.compile("[\U0001F1E6-\U0001F1FF]{2}")
COUNTRY_ALIASES = {"US": ["Съединените щати", "Съединените американски щати"], "GB": ["Обединеното кралство", "Британия"], "RU": ["Руската федерация"],
                   "EU": ["Европейския съюз", "Европейският съюз"], "UN": ["Организацията на обединените нации"], "AE": ["Обединените арабски емирства"],
                   "PS": ["Палестина"], "IR": ["Ислямска република Иран"], "VA": ["Ватикана"]}
SKIP_NAMES = {"ML", "TD", "CD", "CG", "KR", "KP"}   # a common Bulgarian word (Мали, Чад) or one name for two countries (Конго, Корея): found by flag only


def _flag_iso(f):
    return "".join(chr(ord(c) - 0x1F1E6 + 65) for c in f)


def leading_flags(text, valid=None):
    """Flags in the first line of a post, before its first letter or digit ("🇺🇦🇷🇺 …", "❗🇮🇷 …")."""
    m = re.search(r"[0-9A-Za-zА-Яа-яЁё]", text)
    head = text[:m.start()] if m else text
    return [x for x in dict.fromkeys(_flag_iso(f) for f in FLAG_RX.findall(head)) if not valid or x in valid]


def all_flags(text, valid=None):
    return [x for x in dict.fromkeys(_flag_iso(f) for f in FLAG_RX.findall(text)) if not valid or x in valid]


def country_matcher(names):
    """entities.Matcher over the Bulgarian names of the countries (same rules as for people: endings are tolerated, a capital is needed, acronyms are exact)."""
    import entities
    count = collections.Counter(names.values())
    ents = [{"id": "country:" + iso, "type": "country", "name_en": n, "name_bg": n, "aliases": COUNTRY_ALIASES.get(iso, [])}
            for iso, n in names.items() if iso not in SKIP_NAMES and count[n] == 1]
    return entities.Matcher(ents)


def country_meta(posts, texts, names):
    """{post id: (leading flags, other flags, countries named in the text)}; the text part needs the names (map mode)."""
    valid = set(names) or None
    m = country_matcher(names) if names else None
    out = {}
    for pid, _ in posts:
        t = texts.get(str(pid), "")
        lead = leading_flags(t, valid)
        other = [x for x in all_flags(t, valid) if x not in lead]
        tx = [i[8:] for i in m.ids(t)] if m else []
        if lead or other or tx:
            out[str(pid)] = (lead, other, tx)
    return out


def merge_rows(rows, SRC):
    """({post id: arrows}, {post id: (theme, category)}) from the map rows. A post the model split into several events has several rows with the
    same id: the graph is about posts, so their arrows are joined, and theme and category are those of the first (main) row."""
    arrows, meta = {}, {}
    for r in rows:
        pid = str(r[0])
        have = arrows.setdefault(pid, [])
        have += [x for x in row_arrows(r, SRC.get(r[0])) if x not in have]
        meta.setdefault(pid, (r[3], r[7]))                                # theme and category exactly as the map shows them
    return arrows, meta


def map_inputs():
    """The posts, texts and arrows exactly as the map has them (curated rows, hand overrides, model, rules), by reusing build.make_rows()."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import build
    rows, stat, texts, posts, SRC = build.make_rows()
    arrows, meta = merge_rows(rows, SRC)
    tx = {str(k): v for k, v in texts.items()}
    for p in posts:                                                       # posts the map does not place: category by the same rules, no theme
        meta.setdefault(str(p["id"]), ("", build.cat(tx.get(str(p["id"]), ""))))
    return ([(str(p["id"]), p["date"]) for p in posts], tx, arrows, dict(build.BGN), meta)


def legacy_inputs(nodes, edges):
    """The same three things from the older events.json graph (nodes/edges of build())."""
    posts = [(n["id"][5:], n["date"]) for n in nodes if n["type"] == "post"]
    texts = {n["id"][5:]: n["snippet"] for n in nodes if n["type"] == "post"}
    arrows = collections.defaultdict(list)
    for e in edges:
        if e["type"] in ("ATTACKED", "THREATENED"):
            arrows[e["post"][5:]].append((e["source"][8:], e["target"][8:], "A" if e["type"] == "ATTACKED" else "T", "l"))
    return posts, texts, dict(arrows), {}, {}


def load_entity_overrides(data_dir):
    """Hand corrections made in graph.html?edit: every data/entity_overrides*.json, later file names win.
    {"mentions": {post: {"exclude": [ids], "add": [ids]}}, "entities": {id: {name_en, name_bg, type, aliases, not_after}},
     "merge": {id: into id}, "keywords": {post: {"exclude": [kw], "add": [kw]}}}"""
    out = {"mentions": {}, "entities": {}, "merge": {}, "keywords": {}}
    for p in sorted(glob.glob(os.path.join(data_dir, "entity_overrides*.json"))):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            print(f"warning: cannot read {p}: {e}", file=sys.stderr)
            continue
        for k in out:
            if isinstance(d, dict) and isinstance(d.get(k), dict):
                out[k].update(d[k])
    return out


def effective_entities(base, ov):
    """The dictionary with the hand edits on top: changed fields win, an id that is not in the dictionary is a new entity."""
    ents = {e["id"]: dict(e) for e in base}
    for i, o in ov["entities"].items():
        if not isinstance(o, dict):
            continue
        e = ents.setdefault(i, {"id": i, "type": o.get("type", "org"), "name_en": o.get("name_en", i), "name_bg": o.get("name_bg") or o.get("name_en", i), "aliases": []})
        for k in ("type", "name_en", "name_bg", "aliases", "not_after"):
            if o.get(k):
                e[k] = o[k]
    return list(ents.values())


def resolve_merge(merge, known):
    """{from: final target}; unknown targets and loops are ignored."""
    out = {}
    for a in merge:
        b, n = merge[a], 0
        while b in merge and n < 20:
            b, n = merge[b], n + 1
        if a in known and b in known and a != b:
            out[a] = b
    return out


def month_of(d):
    return d[:7] if re.match(r"\d{4}-\d{2}", d or "") else ""


def analyse(posts, texts, arrows, base_ents, ov, meta=None, match=True, cmeta=None):
    """One pass over the posts. Returns the compact records plus, for every entity / pair / arrow type, the ids of its posts (oldest first)."""
    import entities
    ents_all = effective_entities(base_ents, ov)
    known = {e["id"] for e in ents_all}
    merge = resolve_merge(ov["merge"], known)
    ents = sorted((e for e in ents_all if e["id"] not in merge), key=lambda e: e["id"])
    eix = {e["id"]: i for i, e in enumerate(ents)}
    matcher = entities.Matcher(ents_all) if (match and ents_all) else None
    meta = meta or {}
    cmeta = cmeta or {}
    months = sorted({month_of(d) for _, d in posts} - {""})
    mix = {m: i for i, m in enumerate(months)}
    arr_tab, arr_ix = [], {}
    used_th, used_ct = set(), set()
    recs, dates, ent_p, pair_p, arr_p = [], {}, collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
    skey = lambda p: (0, int(p[0])) if str(p[0]).isdigit() else (1, str(p[0]))
    for pid, date in sorted(posts, key=skey):
        pid = str(pid)
        text = texts.get(pid, "")
        ids = matcher.ids(text) if matcher else []
        o = ov["mentions"].get(pid) or {}
        ids = [i for i in ids if i not in (o.get("exclude") or [])] + [i for i in (o.get("add") or []) if i in known]
        ids = list(dict.fromkeys(merge.get(i, i) for i in ids if merge.get(i, i) in eix))
        aa = arrows.get(pid, [])
        cm = cmeta.get(pid) or ([], [], [])
        if not ids and not aa and not any(cm):
            continue
        ai = []
        for x in aa:
            x = list(x)
            if tuple(x) not in arr_ix:
                arr_ix[tuple(x)] = len(arr_tab)
                arr_tab.append(x)
            ai.append(arr_ix[tuple(x)])
        ii = sorted(eix[i] for i in ids)
        th, ct = meta.get(pid, ("", ""))
        used_th.add(th); used_ct.add(ct)
        recs.append([int(pid) if pid.isdigit() else pid, mix.get(month_of(date), -1), ii, ai, 
                     int(date[:10].replace("-", "")) if re.match(r"\d{4}-\d{2}-\d{2}", date or "") else 0, th, ct, list(cm[0]), list(cm[1]), list(cm[2])])
        dates[pid] = (date or "")[:10]
        for i in ii:
            ent_p[i].append(pid)
        for a in range(len(ii)):
            for b in range(a + 1, len(ii)):
                pair_p[(ii[a], ii[b])].append(pid)
        for i in dict.fromkeys(ai):
            arr_p[i].append(pid)
    days = sorted({r[4] for r in recs if r[4]})
    th_tab = [k for k in TH_NAMES if k in used_th] + sorted(k for k in used_th if k and k not in TH_NAMES)
    ct_tab = [k for k in CT_NAMES if k in used_ct] + sorted(k for k in used_ct if k and k not in CT_NAMES)
    for r in recs:                                    # theme and category become positions in the two tables (-1: none)
        r[5] = th_tab.index(r[5]) if r[5] in th_tab else -1
        r[6] = ct_tab.index(r[6]) if r[6] in ct_tab else -1
    return {"ents": ents, "eix": eix, "days": days, "th_tab": th_tab, "ct_tab": ct_tab, "months": months, "arr_tab": arr_tab, "recs": recs, "dates": dates,
            "ent_p": ent_p, "pair_p": pair_p, "arr_p": arr_p, "texts": texts}


def pack(an, names, snip=SNIP, full=True):
    """The JSON for the page. Every post in the page gets its date and the first `snip` characters of its text; the table is gzip+base64
    (the page unpacks it in the background), so the whole list of posts behind any node or line can be shown."""
    sn = {str(r[0]): [an["dates"].get(str(r[0]), ""), " ".join(an["texts"].get(str(r[0]), "").split())[:snip]] for r in an["recs"]}
    snz = base64.b64encode(gzip.compress(json.dumps(sn, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9, mtime=0)).decode("ascii")
    ftz = ""
    if full:                                          # the whole text of every post, lower case, in the order of "posts": read only when someone searches
        ft = [" ".join(an["texts"].get(str(r[0]), "").split()).lower()[:FT_CHARS] for r in an["recs"]]
        ftz = base64.b64encode(gzip.compress(json.dumps(ft, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9, mtime=0)).decode("ascii")
    ents = []
    for i, e in enumerate(an["ents"]):
        ds = sorted(an["dates"][p] for p in an["ent_p"].get(i, []) if an["dates"].get(p))
        ents.append([e["id"], e["type"], e["name_en"], e.get("name_bg") or e["name_en"], len(an["ent_p"].get(i, [])), ds[0] if ds else "", ds[-1] if ds else "", e.get("aliases", [])])
    isos = {x for a in an["arr_tab"] for x in a[:2]} | {x for r in an["recs"] for k in (7, 8, 9) for x in r[k]}
    return {"countries": {c: names.get(c, c) for c in sorted(isos)}, "ents": ents, "themes": [[k, TH_NAMES.get(k, k)] for k in an["th_tab"]], "cats": [[k, CT_NAMES.get(k, k)] for k in an["ct_tab"]], "months": an["months"], "days": an["days"],
            "arrows": an["arr_tab"], "posts": an["recs"], "snz": snz, "ftz": ftz}


def render_page(data, tpl_path):
    html = open(tpl_path, encoding="utf-8").read()
    d3 = os.path.join(ROOT, "assets", "d3.min.js")
    if os.path.exists(d3):
        html = html.replace("<script>__D3__</script>", "<script>" + open(d3, encoding="utf-8").read().replace("</script", "<\\/script") + "</script>")
    else:
        print("warning: assets/d3.min.js is missing, the page will load d3 from the internet", file=sys.stderr)
        html = html.replace("<script>__D3__</script>", '<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>')
    return html.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default="data/events.json")
    ap.add_argument("--curated", default="data/curated.json")
    ap.add_argument("--out", default="data/graph")
    ap.add_argument("--html", default="site/graph.html")
    ap.add_argument("--map", action="store_true", help="take posts and arrows from the map itself (build.make_rows): curated, hand overrides, model, rules")
    ap.add_argument("--entities", default=None, help="entity dictionary (default with --map: data/entities.json)")
    a = ap.parse_args()
    data_dir = os.path.dirname(a.events) or "."
    rows = load(a.events)
    cur = {}
    if os.path.exists(a.curated):
        c = json.load(open(a.curated, encoding="utf-8"))
        if isinstance(c, dict):
            cur = c
        elif not a.map:
            print("note: curated.json is a list of map rows; it is used only with --map (through build.py)", file=sys.stderr)
    meta = load_meta(data_dir)
    nodes, edges = build(rows, cur, meta=meta, keywords=load_keywords(os.path.join(data_dir, "keywords.json")))
    undated = sum(1 for n in nodes if n["type"] == "post" and not n["date"])
    if undated: print(f"warning: {undated} posts have no date/text (not found in data/result_*.json)", file=sys.stderr)
    summ = summarize(edges)
    os.makedirs(a.out, exist_ok=True)
    for name, obj in (("nodes", nodes), ("edges", edges), ("summary", summ)):
        json.dump(obj, open(f"{a.out}/{name}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if a.html:
        posts, texts, arrows, names, meta = map_inputs() if a.map else legacy_inputs(nodes, edges)
        dpath = a.entities or (os.path.join(ROOT, "data", "entities.json") if a.map else None)
        base = json.load(open(dpath, encoding="utf-8"))["entities"] if dpath and os.path.exists(dpath) else []
        ov = load_entity_overrides(os.path.join(ROOT, "data") if a.map else data_dir)
        an = analyse(posts, texts, arrows, base, ov, meta, cmeta=country_meta(posts, texts, names))
        tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graph_template.html")
        os.makedirs(os.path.dirname(a.html) or ".", exist_ok=True)
        for ex, full in ((SNIP, True), (100, True), (60, True), (0, True), (0, False)):
            html = render_page(pack(an, names, ex, full), tpl)
            if len(html.encode("utf-8")) <= PAGE_LIMIT:
                break
        else:
            print(f"warning: page is {len(html) / 1e6:.1f} MB even without texts and text search", file=sys.stderr)
        open(a.html, "w", encoding="utf-8").write(html)
        print(f"page: {len(an['recs'])} posts with entities or arrows, {len(an['ents'])} entities, {len(an['arr_tab'])} arrow types, {len(html) / 1e6:.2f} MB, {ex} characters of text per post{'' if full else ', NO text search (page too big)'}")
    confs = [e["confidence"] for e in edges if "confidence" in e]
    if confs and sum(c >= 0.999 for c in confs) / len(confs) > 0.95:
        print("note: >95% of events have confidence 1.0, so the confidence filter cannot tell good from bad; use tools/audit_sample.py", file=sys.stderr)
    print(f"{len(rows)} posts -> {len(nodes)} nodes, {len(edges)} edges, {len(summ)} aggregated links")


if __name__ == "__main__":
    main()
