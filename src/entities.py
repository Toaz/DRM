"""Find the entities of data/entities.json in a post: rules only, no AI, no network, no tokens.

    import entities
    entities.find(text)   # [{"id", "type", "name_en", "text", "start", "end"}, ...] in reading order
    entities.ids(text)    # unique entity ids of one post, in order of appearance

How an alias is matched (aliases come from name_bg, name_en and "aliases"; "patterns" are extra hand-written regexes):
  - Bulgarian endings are tolerated on every word: Тръмп / Тръмпа / Тръмпът, Шахед / Шахеди / Шахедите.
  - Words written with a capital in the dictionary need a capital in the text ("Град" the weapon, not "град" the city);
    lower-case aliases (хуситите) match in any case.
  - Short upper-case acronyms (ИД, ВСУ, ГРУ, SBU) match exactly, with that case, and with no ending.
  - Designations (С-400, S-400, Ту-95МС, F-16): Cyrillic and Latin look-alike letters are interchangeable, the hyphen is
    optional (but not in one-letter-one-digit ones such as B-1, which must not find "B1 Centauro"), and a short letter suffix is allowed (Су-30 also finds Су-30СМ, but Ми-8 does not find Ми-80).
  - A person written with first name and surname also matches the bare surname ("Уиткоф"), unless two entities share it
    or it is listed in NO_SURNAME. An entity may carry "not_after": words that, written just before a match, cancel it
    (Рифат Асад is not Башар Асад).
  - Links, @names and #tags are ignored. Where aliases overlap, the one that starts first wins, then the longest.
"""
import re, json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
DICT = DATA / "entities.json"

# look-alike letters (upper case); S joins C so that S-400, C-400 and С-400 are one designation
CONF = {"A": "AА", "B": "BВ", "C": "CСS", "E": "EЕ", "H": "HН", "K": "KК", "M": "MМ", "O": "OО", "P": "PР", "T": "TТ", "X": "XХ", "Y": "YУ"}
CLASS = {ch: "[" + g + "]" for g in CONF.values() for ch in g}
FOLD = {ord(ch.lower()): g[0].lower() for g in CONF.values() for ch in g}
FOLD.update({ord(c): "-" for c in "\u2010\u2011\u2013"})

L = "0-9A-Za-zА-Яа-яЁё_"
HY = "[\\-\u2010\u2011\u2013]"
SEP = r"[ \u00a0\t]+"
ENDS = "ските|ската|ското|ския|ите|ата|ята|ото|ето|ски|ска|ско|ът|ят|ия|ом|ем|та|те|то|а|я|у|ю|и|е"
WORD = re.compile(r"[^\W_][\w\u2010\u2011\u2013\-]*")
LEAD = re.compile(r"[^\W\d_]*")
URL = re.compile(r"https?://\S+|t\.me/\S+|@\w+|#\w+")
PREV = re.compile(r"([^\W\d_]+)[\s«»\"„“(\[]*$")
NO_SURNAME = {"остин", "барак", "петро", "austin", "barak", "petro"}  # also a city, another person or a first name


def fold(s):
    return s.lower().translate(FOLD)


def is_designation(tok):
    return bool(re.search(r"\d", tok) and re.search(r"[^\W\d_]", tok))


def is_acronym(alias):
    return " " not in alias and alias.isupper() and 2 <= len(alias) <= 5 and alias.isalpha()


def tok_regex(tok):
    if is_designation(tok):
        hy = r"[\-\u2010\u2011\u2013]" if re.fullmatch(r"[^\W\d_]-\d", tok) else r"[\-\u2010\u2011\u2013 ]?"  # B-1 needs its hyphen: "B1" is another thing
        parts = [hy if c in "-\u2010\u2011\u2013" else CLASS.get(c.upper(), re.escape(c)) for c in tok]
        return "".join(parts) + (r"[A-Za-zА-Яа-я]{0,3}" if tok[-1].isdigit() else "")
    esc = HY.join(re.escape(p) for p in tok.split("-"))
    if len(tok) >= 3 and re.search(r"[А-Яа-яЁё]$", tok):
        alts = f"{esc}(?:{ENDS})?"
        if tok.endswith(("ър", "ъл")):  # Калибър -> Калибри
            alts = f"(?:{alts}|{HY.join(re.escape(p) for p in (tok[:-2] + tok[-1]).split('-'))}(?:{ENDS}))"
        return alts
    return esc


class Alias:
    __slots__ = ("ent", "text", "rx", "caps", "key")

    def __init__(self, ent, text):
        self.ent, self.text = ent, text
        toks = text.split()
        if is_acronym(text):
            self.rx, self.caps = re.compile(rf"(?<![{L}]){re.escape(text)}(?![{L}])"), ()
        else:
            self.rx = re.compile(rf"(?<![{L}])" + SEP.join(tok_regex(t) for t in toks) + rf"(?![{L}])", re.I)
            self.caps = tuple(bool(t[0].isupper()) and not is_designation(t) for t in toks)
        self.key = fold(LEAD.match(toks[0]).group())[:3]

    def match(self, text, pos):
        m = self.rx.match(text, pos)
        if m and any(self.caps):
            words = m.group().split()
            if len(words) == len(self.caps) and any(c and not w[0].isupper() for c, w in zip(self.caps, words)):
                return None
        return m


class Matcher:
    def __init__(self, entities):
        self.ents, self.index, self.free, self.owners = {}, {}, [], {}
        for e in entities:
            self.ents[e["id"]] = e
            for a in dict.fromkeys(a.strip() for a in [*e.get("aliases", []), e.get("name_bg", ""), e.get("name_en", "")] if a and a.strip()):
                al = Alias(e["id"], a)
                self.index.setdefault(al.key, []).append(al)
                self.owners.setdefault(" ".join(fold(a).split()), (a, set()))[1].add(e["id"])
            for p in e.get("patterns", []):
                self.free.append((e["id"], re.compile(p, re.I)))
        self.not_after = {e["id"]: {w.lower() for w in e["not_after"]} for e in entities if e.get("not_after")}
        self._add_surnames(entities)

    def _add_surnames(self, entities):
        found, banned = {}, {fold(w) for w in NO_SURNAME}
        for e in entities:
            if e["type"] != "person":
                continue
            for a in [*e.get("aliases", []), e.get("name_bg", ""), e.get("name_en", "")]:
                t = a.split()
                if len(t) >= 2 and len(t[-1]) >= 5 and t[-1].isalpha() and t[-1][0].isupper() and fold(t[-1]) not in banned:
                    found.setdefault(fold(t[-1]), {})[e["id"]] = t[-1]
        for k, owners in found.items():
            if len(owners) == 1 and k not in self.owners:
                (ent, s), = owners.items()
                al = Alias(ent, s)
                self.index.setdefault(al.key, []).append(al)
                self.owners[k] = (s, {ent})

    @property
    def collisions(self):
        """Aliases that belong to more than one entity: {alias: [ids]}. The first entity in the dictionary wins."""
        return {a: sorted(i) for a, i in self.owners.values() if len(i) > 1}

    def find(self, text):
        text = URL.sub(lambda m: " " * len(m.group()), text)
        cands = []
        for w in WORD.finditer(text):
            run = fold(LEAD.match(w.group()).group())
            best = None
            for k in dict.fromkeys((run[:3], run[:2], run[:1])):
                for al in self.index.get(k, ()):
                    m = al.match(text, w.start())
                    if m and al.ent in self.not_after:
                        pm = PREV.search(text[max(0, w.start() - 40):w.start()])
                        if pm and pm.group(1).lower() in self.not_after[al.ent]:
                            m = None
                    if m and (best is None or m.end() > best[0].end()):
                        best = (m, al)
            if best:
                cands.append((best[0].start(), best[0].end(), best[1].ent))
        for ent, rx in self.free:
            cands += [(m.start(), m.end(), ent) for m in rx.finditer(text)]
        out, last = [], 0
        for s, e, ent in sorted(cands, key=lambda c: (c[0], -(c[1] - c[0]))):
            if s >= last:
                d = self.ents[ent]
                out.append({"id": ent, "type": d["type"], "name_en": d["name_en"], "text": text[s:e], "start": s, "end": e})
                last = e
        return out

    def ids(self, text):
        return list(dict.fromkeys(m["id"] for m in self.find(text)))


_cache = {}


def load(path=DICT):
    """The matcher for data/entities.json (built once per run)."""
    if path not in _cache:
        _cache[path] = Matcher(json.load(open(path, encoding="utf-8"))["entities"])
    return _cache[path]


def find(text):
    return load().find(text)


def ids(text):
    return load().ids(text)
