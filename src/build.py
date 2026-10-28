"""Build site/index.html from data/*.json.  Run:  python src/build.py"""
import json, re, sys, collections, gzip, base64, hashlib, math, gettext, difflib, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import pycountry
from common import ROOT, load_all, txt
from place import *          # PT, ISO3, theme, locate, detect ...
from cats import RX
import arrows as AR, extract, geo

BGN = {}
_tr = gettext.translation("iso3166-1", pycountry.LOCALES_DIR, languages=["bg"])
for c in pycountry.countries:
    BGN[c.alpha_2] = _tr.gettext(c.name).split(",")[0]
BGN.update({"US": "САЩ", "RU": "Русия", "GB": "Великобритания", "KR": "Южна Корея", "KP": "Северна Корея", "IR": "Иран",
            "SY": "Сирия", "PS": "Палестина", "VE": "Венецуела", "TR": "Турция", "AE": "ОАЕ", "MD": "Молдова", "RS": "Сърбия",
            "BY": "Беларус", "CD": "ДР Конго", "TW": "Тайван", "EU": "ЕС", "UN": "ООН", "CZ": "Чехия", "MK": "Северна Македония",
            "IL": "Израел", "YE": "Йемен", "IQ": "Ирак", "SA": "Саудитска Арабия", "LB": "Ливан", "UA": "Украйна", "CN": "Китай", "JP": "Япония"})
EU27 = ['040', '056', '100', '191', '196', '203', '208', '233', '246', '250', '276', '300', '348', '372', '380', '428', '440', '442',
        '528', '616', '620', '642', '703', '705', '724', '752']
AV = re.compile(r'самолет|полет|авиац|въздушно пространство|летище|пилот|airspace|aircraft|flight|хеликоптер|вертолет', re.I)
NT = 360   # characters of each post kept in the page; the full text opens on Telegram
OPEN_TARGET = 'посоченото място'   # arrow label when the target is the place named in the post (ship at sea, ...)
PLACE_FROM_LLM = True   # True: the place name the model found ("Kharkiv") is looked up and wins over the keyword city list; False: old behaviour
GAZ = geo.Gazetteer(CI.values())   # every city geonamescache knows, by all its names
MENTIONED_IN_FILTER = True   # True: a post also appears under every country the model found in it, not only its location/arrows
FULL_TEXT_SEARCH = True   # True: the page also carries the full text of every post (compressed, read only when someone searches); False: search sees only the 360-character snippet
FLAGS_INVOLVE = True   # True: every country whose flag is anywhere in a post counts as involved (it flashes and is found by the country filter); flags never make an attacker or move an arrow
CLUSTER = True   # True: posts with the same attacker, target and day get a group number, so the page can count them as one event


FLAG = re.compile('[\U0001F1E6-\U0001F1FF]{2}')


def flag_isos(text):
    """Countries whose flag emoji is in the text, in order of appearance (a flag is two regional-indicator letters = the ISO code)."""
    out = []
    for f in FLAG.findall(text):
        iso = ''.join(chr(ord(c) - 0x1F1E6 + 65) for c in f)
        if (iso in ISO3 or iso == 'EU') and iso not in out:
            out.append(iso)
    return out


def ids(iso):
    return EU27 if iso == 'EU' else ([ISO3[iso]] if iso in ISO3 else [])


def cat(t):
    for k, n, r in RX:
        if k == 'sea' and AV.search(t) and not r.search(t):
            return 'avi'
        if r.search(t):
            return k
    return 'avi' if AV.search(t) else 'gen'


def jit(i, rad):
    h = int(hashlib.md5(str(i).encode()).hexdigest()[:8], 16)
    a = (h % 3600) / 3600 * 6.283
    r = rad * (0.25 + 0.75 * ((h >> 12) % 1000) / 1000)
    return r * math.sin(a) * .7, r * math.cos(a)


def llm_row(rec, t, tt, i, d16, ex, L, stat, ov_ev=None, use_model=True):
    """Row for a post the model has read (arrows may be several), or None if the post cannot be placed.

    ov_ev: arrows made by hand (data/overrides*.json) that replace the model's arrows. use_model False: rec is not a model result."""
    G = geo.place_for(rec, GAZ) if (PLACE_FROM_LLM and use_model) else None
    if G:                                                         # a place the model named and the city list confirms, inside a country we trust
        stat['place from model'] += 1
        if L and L[3] == 'p' and L[2] and geo.km(L[:2], G[:2]) > 150:
            stat['place: model differs from city list (>150 km)'] += 1
        L = G
    every = extract.with_show([dict(e) for e in rec['ev']]) if ov_ev is None else ov_ev   # thresholds are applied now, so changing them needs no new model run
    ev = AR.visible(every)
    stat['hidden arrows'] += len(every) - len(ev)
    arr, skipped = AR.plan(ev, PT, L if L and L[3] == 'p' else None)
    arr = AR.main_first(arr, rec.get('loc'))
    stat['arrows skipped (no coordinates)'] += len(skipped)
    mentioned = rec['c'] if MENTIONED_IN_FILTER else []
    c = cat(t)
    if c == 'gen' and rec.get('cat'):
        c = rec['cat']
    if arr:
        main = arr[0]
        conf = main['conf']
        dy, dx = jit(i, .2 if conf == 'p' else 1.2)           # every arrow of the post moves by the same offset
        la, lo = round(main['dest'][0] + dy, 2), round(main['dest'][1] + dx, 2)
        lst = [[round(a['org'][0], 2), round(a['org'][1], 2), round(a['dest'][0] + dy, 2), round(a['dest'][1] + dx, 2),
                BGN.get(a['from'], a['from']) + ' \u2192 ' + (OPEN_TARGET if a['open'] else BGN.get(a['to'], a['to'])), a['kind'], a['from']] for a in arr]
        att, inv = AR.country_ids(arr, mentioned, ids, rec.get('loc'))
        stat['arrow'] += 1
        stat['post with several arrows'] += len(arr) > 1
        ids_ = [[a['from'], '' if a['open'] else a['to']] for a in arr]       # which countries each arrow joins (the page needs them to edit arrows)
        return [i, la, lo, theme(main['to']), conf, None, tt, c, lst, d16, att, inv, ex, ids_]
    # no arrow: an exact place found by the old city list wins, otherwise the country the model named, otherwise the old guess
    if not (L and L[3] == 'p') and rec.get('loc') in PT:
        L = (PT[rec['loc']][0], PT[rec['loc']][1], rec['loc'], 'a')
    if not L:
        return None
    la, lo, iso, conf = L
    dy, dx = jit(i, .25 if conf == 'p' else 1.6 if conf == 'a' else .7)
    _, inv = AR.country_ids([], mentioned, ids, iso)
    stat['placed'] += 1
    return [i, round(la + dy, 2), round(lo + dx, 2), theme(iso), conf, None, tt, c, None, d16, [], inv, ex]


def load_overrides():
    """Arrows made by hand: every data/overrides*.json file, later file names win. {post id: [(from, to or None, 'p' or 'v')]}.
    File format: {"20136": {"arrows": [["IR", "", "p"]]}, "19943": {"arrows": []}}  ("" = the place named in the post, [] = no arrow)."""
    out = {}
    for f in sorted((ROOT / 'data').glob('overrides*.json')):
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception as e:
            print('WARNING: cannot read', f.name, '-', e)
            continue
        for k, v in d.items():
            arrs = v.get('arrows') if isinstance(v, dict) else None
            if not isinstance(arrs, list):
                print('WARNING: bad entry', k, 'in', f.name)
                continue
            out[str(k)] = [(a[0], (a[1] or None) if len(a) > 1 else None, 'v' if len(a) > 2 and a[2] == 'v' else 'p') for a in arrs if a and a[0]]
    return out


def ov_events(arrs):
    return [{'from': a, 'to': b, 'kind': 'verbal' if k == 'v' else 'physical', 'confidence': 1.0, 'show': True} for a, b, k in arrs]


def curated_arrows(r, arrs, stat):
    """A hand-placed row keeps its place; only its arrows are replaced by the hand-made ones."""
    lst, ids_ = [], []
    for a, b, k in arrs:
        if a not in PT or (b and b not in PT):
            stat['override arrows skipped (no coordinates)'] += 1
            continue
        dest = (r[1], r[2]) if (not b or r[4] == 'p') else PT[b]
        lst.append([round(PT[a][0], 2), round(PT[a][1], 2), round(dest[0], 2), round(dest[1], 2),
                    BGN.get(a, a) + ' \u2192 ' + (OPEN_TARGET if not b else BGN.get(b, b)), k, a])
        ids_.append([a, b or ''])
    r[8] = lst or None
    r[10] = AR.unique(i for a, b in ids_ for i in ids(a))                                           # the page colours by the first attacker
    r[11] = AR.unique([i for a, b in ids_ if b for i in ids(b)] + list(r[11] or []))
    return r[:13] + [ids_ or None]


def match_curated(cur, texts, stat):
    """Which post is each hand-placed row? Returns ({post id: row}, rows that match no post).

    Tried in this order: the first 60 characters of the text (as before); the post id kept in the row (only if the text is alike,
    so an old row number cannot catch another post); a close match of the text start, which survives a small edit of the opening.
    Run `python src/build.py --fix-curated` once to write the real post ids into data/curated.json."""
    norm = lambda s: ' '.join(s.split())[:60]
    by_text = collections.defaultdict(list)
    for pid, t in texts.items():
        by_text[norm(t)].append(pid)
    keys = list(by_text)
    out, used, lost = {}, set(), []
    for r in cur:
        snip = ' '.join((r[6] or '').split())
        pid = how = None
        c = [p for p in by_text.get(norm(snip), []) if p not in used]
        if c:
            pid, how = c[0], 'text'
        elif r[0] in texts and r[0] not in used and difflib.SequenceMatcher(None, snip[:120], texts[r[0]][:120]).ratio() >= .6:
            pid, how = r[0], 'post id'
        else:
            s40 = snip[:40]
            c = [p for p, t in texts.items() if p not in used and len(s40) >= 25 and s40 in t[:300]]      # something was added before the old opening
            if c:
                pid, how = max(c, key=lambda p: difflib.SequenceMatcher(None, snip[:150], texts[p][:150]).ratio()), 'opening moved'
            else:
                for k in difflib.get_close_matches(norm(snip), keys, n=3, cutoff=.85):
                    c = [p for p in by_text[k] if p not in used]
                    if c:
                        pid, how = c[0], 'close text'
                        break
        if pid is None:
            lost.append(r)
            continue
        used.add(pid)
        out[pid] = r
        stat['hand-placed matched by ' + how] += 1
    return out, lost


def assign_clusters(rows, stat):
    """Posts with the same attacker, the same target and the same day describe one event: give them a group number (row field 14)."""
    g = collections.defaultdict(list)
    for r in rows:
        if r[8] and r[8][0][5] == 'p' and len(r) > 13 and r[13] and r[13][0][1] not in ('', '?'):
            g[(r[13][0][0], r[13][0][1], r[9][:10])].append(r)
    n = 0
    for k in sorted(g):
        if len(g[k]) < 2:
            continue
        n += 1
        for r in g[k]:
            r.append(n)
            stat['posts in event groups'] += 1
    stat['event groups'] = n


def main():
    posts = [m for m in load_all() if len(txt(m).strip()) > 20]
    cur = json.load(open(ROOT / 'data/curated.json', encoding='utf-8'))
    rows, stat = [], collections.Counter()
    texts = {x['id']: ' '.join(txt(x).split()) for x in posts}
    curmap, lost = match_curated(cur, texts, stat)    # hand-placed posts: {post id: row}
    if '--fix-curated' in sys.argv:                   # write the real post ids into curated.json, so later edits of the text cannot break the match
        (ROOT / 'data/curated.json.bak').write_text((ROOT / 'data/curated.json').read_text(encoding='utf-8'), encoding='utf-8')
        for pid, r in curmap.items():
            r[0] = pid
        (ROOT / 'data/curated.json').write_text(json.dumps(cur, ensure_ascii=False), encoding='utf-8')
        print('curated.json: post ids written for', len(curmap), 'rows (backup: curated.json.bak)')
    for r in lost:
        print('WARNING: hand-placed row matches no post:', r[0], '|', ' '.join((r[6] or '').split())[:70])
    OVR = load_overrides()                            # arrows made by hand
    EV = extract.load_cache()['posts']             # what the model found, by post id
    for x in posts:
        i = x['id']
        t = texts[i]
        ex = int('\u2757' in t or '\u203c' in t)
        d16 = x['date'][:16]
        ov = OVR.get(str(i))
        if i in curmap:
            r = list(curmap[i]); r[0] = i; r[5] = None; r[9] = d16; r = r[:12] + [ex]; r[8] = [r[8]] if r[8] else None
            if ov is not None:
                r = curated_arrows(r, ov, stat); stat['arrows by hand'] += 1
            else:
                r.append([[a[6], '?'] for a in r[8]] if r[8] else None)     # the target of an old hand-placed arrow is not known
            rows.append(r); stat['hand-placed'] += 1
            continue
        L = locate(t)
        tt = t[:NT] + ('\u2026' if len(t) > NT else '')
        rec = EV.get(str(i))
        fresh = bool(rec and rec.get('h') == extract.text_hash(txt(x).strip()))
        if ov is not None:                                   # arrows made by hand win over the model and the keyword rules
            if not fresh:
                D0 = detect(t, L[2] if L else None)
                rec = {'ev': [], 'c': [], 'loc': L[2] if L else (D0[1][2] if D0 else None)}
            row = llm_row(rec, t, tt, i, d16, ex, L, stat, ov_ev=ov_events(ov), use_model=fresh)
            rows.append(row) if row else stat.update(unplaced=1)
            stat['arrows by hand'] += 1
            stat['read by model'] += fresh
            continue
        if fresh:                                            # an edited post is read again, until then the old rules apply
            row = llm_row(rec, t, tt, i, d16, ex, L, stat)
            if row:
                rows.append(row)
            else:
                stat['unplaced'] += 1
            stat['read by model'] += 1
            continue
        loc = L[2] if L else None
        D = detect(t, loc)
        if D:
            a_iso, tg, kind = D
            t_iso = tg[2]
            la, lo = tg[3] if tg[3] else PT[t_iso]
            conf, dj = ('p', .2) if tg[3] else ('a', 1.2)
            dy, dx = jit(i, dj)
            la, lo = round(la + dy, 2), round(lo + dx, 2)
            oa, oo = PT[a_iso]
            rows.append([i, la, lo, theme(t_iso), conf, None, tt, cat(t),
                         [[oa, oo, la, lo, BGN.get(a_iso, a_iso) + ' \u2192 ' + BGN.get(t_iso, t_iso), kind, a_iso]],
                         d16, ids(a_iso), ids(t_iso), ex, [[a_iso, t_iso]]])
            stat['arrow'] += 1
            continue
        if not L:
            stat['unplaced'] += 1
            continue
        la, lo, iso, conf = L
        dy, dx = jit(i, .25 if conf == 'p' else 1.6 if conf == 'a' else .7)
        rows.append([i, round(la + dy, 2), round(lo + dx, 2), theme(iso), conf, None, tt, cat(t), None, d16, [], ids(iso), ex])
        stat['placed'] += 1
    if FLAGS_INVOLVE:                                # flags name countries even when the words do not: involved only, never attacker, arrows stay where they are
        for r in rows:
            inv = list(r[11] or [])
            add = AR.unique(i for iso in flag_isos(texts[r[0]]) for i in ids(iso) if i not in inv)
            if add:
                r[11] = inv + add
                stat['posts with countries added by flags'] += 1
    rows.sort(key=lambda r: r[0])
    if CLUSTER:
        assign_clusters(rows, stat)
    raw = json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()
    b64 = base64.b64encode(gzip.compress(raw, 9)).decode()
    last = rows[-1][9][:10]
    y, mm, d = last.split('-')
    mo = ['януари', 'февруари', 'март', 'април', 'май', 'юни', 'юли', 'август', 'септември', 'октомври', 'ноември', 'декември']
    full = ''
    if FULL_TEXT_SEARCH:                              # the whole text of each post, in row order, read by the page only when someone searches
        full = base64.b64encode(gzip.compress(json.dumps([texts[r[0]].lower() for r in rows], ensure_ascii=False, separators=(',', ':')).encode(), 9)).decode()
    isoj = json.dumps({k: [BGN.get(k, k), round(v[0], 2), round(v[1], 2)] for k, v in PT.items()}, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')   # for the arrow editor
    fmt = lambda n: '{:,}'.format(n).replace(',', ' ')
    html = (ROOT / 'template/template.html').read_text(encoding='utf-8')
    A = ROOT / 'assets'
    html = (html.replace('__B64__', b64).replace('__FULL__', full).replace('__ISO__', isoj).replace('__MAP__', (A / 'land.html').read_text(encoding='utf-8'))
            .replace('__GRAT__', (A / 'grat.txt').read_text()).replace('__LBL__', (A / 'lbl.json').read_text(encoding='utf-8'))
            .replace('__AI__', fmt(stat['read by model'])).replace('__TOTAL__', fmt(len(posts))).replace('__UNPLACED__', fmt(stat['unplaced'])).replace('__LAST__', f'{int(d)} {mo[int(mm) - 1]} {y}'))
    out = ROOT / 'site'
    out.mkdir(exist_ok=True)
    (out / 'index.html').write_text(html, encoding='utf-8')
    (out / '.nojekyll').write_text('')
    print(dict(stat), '| rows', len(rows), '| posts with arrows', sum(1 for r in rows if r[8]), '| arrows', sum(len(r[8]) for r in rows if r[8]), '| last post', rows[-1][9],
          '| page %.2f MB' % (len(html) / 1e6))


if __name__ == '__main__':
    main()
