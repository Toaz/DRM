"""How reliable are the arrows on the map?  Measures BOTH kinds of mistake.

  python tools/audit_map.py --n 40            writes data/audit_map.csv: half posts WITH a drawn arrow, half posts WITHOUT one
  (open the file, open each link, write y or n in the column 'ok', optionally the right answer in 'should_be')
  python tools/audit_map.py --score           prints the results with a 95% interval and lists every 'n'

  ok = y  means the model's answer is right:  for an arrow row "this arrow is correct", for a no-arrow row "there really is no attack or threat".
  Rows without an ok are ignored, so you can score a partly filled file.

Only posts the model has read (data/events.json, text unchanged) are sampled. The no-arrow rows lean towards posts that contain attack words,
because that is where a missed arrow hides; the number for them is a 'miss rate among suspicious posts', not among all posts.
Needs nothing but the standard library.
"""
import argparse, csv, json, math, random, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from common import load_all, txt            # noqa: E402
import extract                              # noqa: E402

ATTACK_WORDS = re.compile(r"удар|атак|обстрел|дрон|ракет|нападен|бомбард|порази|взрив|strike|attack|missile|drone", re.I)
FIELDS = ["post_url", "kind", "claim", "model_reason", "text", "ok", "should_be"]


def wilson(k, n, z=1.96):
    """95% confidence interval for k successes in n trials (better than k/n when n is small or k is 0 or n)."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def candidates(posts, cache, since=""):
    """(arrow_rows, none_rows): one row per drawn arrow, one per read post that has none."""
    arrow, none = [], []
    for m in posts:
        t = txt(m).strip()
        rec = cache["posts"].get(str(m["id"]))
        if not rec or rec.get("h") != extract.text_hash(t) or m["date"][:10] < since:
            continue
        url = f"https://t.me/drmjournal/{m['id']}"
        shown = [e for e in extract.with_show([dict(e) for e in rec["ev"]]) if e["show"]]
        for e in shown:
            claim = f"{e['from']} -> {e['to'] or '(place named in the post)'} [{e['kind']}, {e['confidence']:.2f}]"
            arrow.append({"post_url": url, "kind": "arrow", "claim": claim, "model_reason": e.get("why", ""), "text": " ".join(t.split())[:420]})
        if not shown:
            none.append({"post_url": url, "kind": "no arrow", "claim": "(no attack or threat)", "model_reason": "",
                         "text": " ".join(t.split())[:420], "_suspicious": bool(ATTACK_WORDS.search(t))})
    return arrow, none


def pick(arrow, none, n, seed=1):
    rnd = random.Random(seed)
    half = n // 2
    sus = [r for r in none if r["_suspicious"]]
    rest = [r for r in none if not r["_suspicious"]]
    take_none = rnd.sample(sus, min(len(sus), n - half))
    take_none += rnd.sample(rest, min(len(rest), n - half - len(take_none)))     # fill up if there are too few suspicious ones
    rows = rnd.sample(arrow, min(len(arrow), half)) + take_none
    return [{k: v for k, v in r.items() if k != "_suspicious"} for r in rows]      # copies: the input rows stay untouched


def score(rows):
    """-> {'arrow': (good, total), 'no arrow': (good, total)} counting only rows marked y or n."""
    out = {"arrow": [0, 0], "no arrow": [0, 0]}
    for r in rows:
        ok = (r.get("ok") or "").strip().lower()
        if ok in ("y", "n") and r["kind"] in out:
            out[r["kind"]][1] += 1
            out[r["kind"]][0] += ok == "y"
    return {k: tuple(v) for k, v in out.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=40, help="rows to sample (half arrows, half no-arrow posts)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--since", default="", help="only posts from this date, YYYY-MM-DD")
    ap.add_argument("--csv", default=str(ROOT / "data" / "audit_map.csv"))
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    if a.score:
        rows = list(csv.DictReader(open(a.csv, encoding="utf-8")))
        res = score(rows)
        for kind, label in (("arrow", "drawn arrows that are correct"), ("no arrow", "no-arrow posts that really have no attack")):
            g, n = res[kind]
            lo, hi = wilson(g, n)
            print(f"{label}: {g}/{n}" + (f" = {100 * g / n:.0f}%  (95% interval {100 * lo:.0f}-{100 * hi:.0f}%)" if n else "  (nothing marked yet)"))
        for r in rows:
            if (r.get("ok") or "").strip().lower() == "n":
                print(f"  WRONG  {r['post_url']}  {r['claim']}  ->  {r.get('should_be') or '?'}")
        return
    posts = load_all()
    arrow, none = candidates(posts, extract.load_cache(), a.since)
    rows = pick(arrow, none, a.n, a.seed)
    with open(a.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({**r, "ok": "", "should_be": ""})
    print(f"{len(arrow)} drawn arrows and {len(none)} no-arrow posts available; wrote {len(rows)} rows to {a.csv}.\n"
          f"Open each link, write y or n in the 'ok' column, then run with --score.")


if __name__ == "__main__":
    main()
