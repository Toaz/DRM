"""Show what the model found, next to the post text, so you can judge it.

  python3 tools/show_events.py            # the 10 newest analysed posts
  python3 tools/show_events.py --n 30     # the 30 newest
  python3 tools/show_events.py --id 20132 # one post
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import extract
from common import load_all, txt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--id", type=int)
    a = ap.parse_args()
    cache = extract.load_cache()["posts"]
    if not cache:
        sys.exit("data/events.json is empty or missing. Run: python3 src/extract.py --limit 5")
    posts = {m["id"]: m for m in load_all()}
    ids = [a.id] if a.id else sorted((int(k) for k in cache), reverse=True)[: a.n]
    for i in ids:
        rec, m = cache.get(str(i)), posts.get(i)
        if not rec or not m:
            print(f"#{i}: not analysed yet" if not rec else f"#{i}: post not found in data/")
            continue
        text = " ".join(txt(m).split())
        print(f"#{i}  {m['date'][:16].replace('T', ' ')}  https://t.me/drmjournal/{i}")
        print("   " + text[:400] + ("..." if len(text) > 400 else ""))
        ev = extract.with_show([dict(e) for e in rec["ev"]])
        arrows = "; ".join(f"{e['from']}->{e['to']} ({e['kind']}, {e['confidence']}, {'drawn' if e['show'] else 'HIDDEN'})  {e['why']}" for e in ev)
        print(f"   countries: {' '.join(rec['c']) or '-'}  |  location: {rec['loc'] or '-'}  |  category: {rec['cat'] or '-'}")
        print(f"   arrows: {arrows or 'none'}\n")


if __name__ == "__main__":
    main()
