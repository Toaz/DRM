"""Check the entity matcher by eye, and look at the dictionary through the posts.

  python tools/audit_entities.py --n 60        # sample matches -> data/audit_entities.tsv (put y or n in the "ok" column)
  python tools/audit_entities.py --score       # precision per type, and the aliases that cause the wrong matches
  python tools/audit_entities.py --stats       # mentions per entity; entries never found; the most frequent ones
  python tools/audit_entities.py --check       # aliases that belong to more than one entity
  python tools/audit_entities.py --show 12345  # what is found in one post (id)

The sample takes at most 2 matches per entity, so a frequent name (Trump) cannot fill it. Same seed, same sample.
"""
import sys, csv, random, argparse, collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from common import DATA, load_all, txt
import entities

TSV = DATA / "audit_entities.tsv"


def flat(t, s, e, w=70):
    return (" ".join(t[max(0, s - w):s].split()) + " «" + t[s:e] + "» " + " ".join(t[e:e + w].split())).strip()


def mentions(posts, m):
    for p in posts:
        t = txt(p)
        for x in m.find(t):
            yield p["id"], t, x


def sample(posts, m, n, seed):
    by = collections.defaultdict(list)
    for pid, t, x in mentions(posts, m):
        by[x["id"]].append((pid, t, x))
    rnd = random.Random(seed)
    pool = [r for rows in by.values() for r in rnd.sample(rows, min(2, len(rows)))]
    return rnd.sample(pool, min(n, len(pool)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--show", type=int, default=0)
    a = ap.parse_args()
    m = entities.load()
    if a.check:
        c = m.collisions
        print(f"{len(c)} aliases belong to more than one entity (the first in the dictionary wins):")
        for k, v in c.items():
            print(" ", k, v)
    elif a.score:
        rows = list(csv.DictReader(open(TSV, encoding="utf-8"), delimiter="\t"))
        done = [r for r in rows if r["ok"].strip().lower() in ("y", "n")]
        print(f"{len(done)} of {len(rows)} rows marked")
        by = collections.defaultdict(lambda: [0, 0])
        for r in done:
            by[r["type"]][r["ok"].strip().lower() == "y"] += 1
        for t, (bad, good) in sorted(by.items()):
            print(f"  {t:7} {good}/{good + bad} right")
        tot = sum(v[1] for v in by.values())
        print(f"  all     {tot}/{len(done)} right" + (f" = {100 * tot // len(done)}%" if done else ""))
        for r in done:
            if r["ok"].strip().lower() == "n":
                print(f"  WRONG {r['entity']}  matched «{r['matched']}»  | {r['context'][:110]}")
    elif a.stats:
        posts = load_all()
        cnt = collections.Counter(x["id"] for _, _, x in mentions(posts, m))
        print(f"{len(posts)} posts, {sum(cnt.values())} mentions, {len(cnt)} of {len(m.ents)} entities found")
        print("most frequent:", ", ".join(f"{m.ents[i]['name_en']} {n}" for i, n in cnt.most_common(30)))
        print("never found:", ", ".join(e["name_en"] for i, e in m.ents.items() if i not in cnt))
    elif a.show:
        p = next((p for p in load_all() if p["id"] == a.show), None)
        if not p:
            sys.exit("no such post id")
        for x in m.find(txt(p)):
            print(x["type"], x["name_en"], "<-", x["text"])
    elif a.n:
        rows = sample(load_all(), m, a.n, a.seed)
        with open(TSV, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["ok", "type", "entity", "matched", "post", "context"])
            for pid, t, x in sorted(rows, key=lambda r: (r[2]["type"], r[2]["name_en"])):
                w.writerow(["", x["type"], x["name_en"], x["text"], pid, flat(t, x["start"], x["end"])])
        print(f"{len(rows)} matches -> {TSV}\nOpen it, write y (right) or n (wrong) in the first column, save, then run --score.")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
