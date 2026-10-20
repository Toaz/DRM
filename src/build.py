"""Build site/index.html from data/*.json.  Run:  python src/build.py"""
import json, re, sys, collections, gzip, base64, hashlib, math, gettext, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import pycountry
from common import ROOT, load_all, txt
from place import *          # PT, ISO3, theme, locate, detect ...
from cats import RX

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


def main():
    posts = [m for m in load_all() if len(txt(m).strip()) > 20]
    cur = json.load(open(ROOT / 'data/curated.json', encoding='utf-8'))
    norm = lambda s: ' '.join(s.split())[:60]
    curmap = {norm(r[6]): r for r in cur}          # hand-placed posts, matched by their text
    rows, stat = [], collections.Counter()
    for x in posts:
        t = ' '.join(txt(x).split())
        i = x['id']
        ex = int('\u2757' in t or '\u203c' in t)
        d16 = x['date'][:16]
        if norm(t) in curmap:
            r = list(curmap[norm(t)]); r[0] = i; r[5] = None; r[9] = d16; r = r[:12] + [ex]
            rows.append(r); stat['hand-placed'] += 1
            continue
        L = locate(t)
        loc = L[2] if L else None
        D = detect(t, loc)
        tt = t[:NT] + ('\u2026' if len(t) > NT else '')
        if D:
            a_iso, tg, kind = D
            t_iso = tg[2]
            la, lo = tg[3] if tg[3] else PT[t_iso]
            conf, dj = ('p', .2) if tg[3] else ('a', 1.2)
            dy, dx = jit(i, dj)
            la, lo = round(la + dy, 2), round(lo + dx, 2)
            oa, oo = PT[a_iso]
            rows.append([i, la, lo, theme(t_iso), conf, None, tt, cat(t),
                         [oa, oo, la, lo, BGN.get(a_iso, a_iso) + ' \u2192 ' + BGN.get(t_iso, t_iso), kind, a_iso],
                         d16, ids(a_iso), ids(t_iso), ex])
            stat['arrow'] += 1
            continue
        if not L:
            stat['unplaced'] += 1
            continue
        la, lo, iso, conf = L
        dy, dx = jit(i, .25 if conf == 'p' else 1.6 if conf == 'a' else .7)
        rows.append([i, round(la + dy, 2), round(lo + dx, 2), theme(iso), conf, None, tt, cat(t), None, d16, [], ids(iso), ex])
        stat['placed'] += 1
    rows.sort(key=lambda r: r[0])
    raw = json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()
    b64 = base64.b64encode(gzip.compress(raw, 9)).decode()
    last = rows[-1][9][:10]
    y, mm, d = last.split('-')
    mo = ['януари', 'февруари', 'март', 'април', 'май', 'юни', 'юли', 'август', 'септември', 'октомври', 'ноември', 'декември']
    fmt = lambda n: '{:,}'.format(n).replace(',', ' ')
    html = (ROOT / 'template/template.html').read_text(encoding='utf-8')
    A = ROOT / 'assets'
    html = (html.replace('__B64__', b64).replace('__MAP__', (A / 'land.html').read_text(encoding='utf-8'))
            .replace('__GRAT__', (A / 'grat.txt').read_text()).replace('__LBL__', (A / 'lbl.json').read_text(encoding='utf-8'))
            .replace('__TOTAL__', fmt(len(posts))).replace('__UNPLACED__', fmt(stat['unplaced'])).replace('__LAST__', f'{int(d)} {mo[int(mm) - 1]} {y}'))
    out = ROOT / 'site'
    out.mkdir(exist_ok=True)
    (out / 'index.html').write_text(html, encoding='utf-8')
    (out / '.nojekyll').write_text('')
    print(dict(stat), '| rows', len(rows), '| arrows', sum(1 for r in rows if r[8]), '| last post', rows[-1][9],
          '| page %.2f MB' % (len(html) / 1e6))


if __name__ == '__main__':
    main()
