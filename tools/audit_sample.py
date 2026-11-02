"""Reliability check: random sample of events -> CSV to mark y/n -> accuracy.
  python tools/audit_sample.py --n 40          writes data/audit.csv (fill the 'ok' column with y or n)
  python tools/audit_sample.py --score         prints accuracy from the filled file"""
import argparse, csv, json, random
ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=40); ap.add_argument("--score", action="store_true")
ap.add_argument("--graph", default="data/graph"); ap.add_argument("--csv", default="data/audit.csv"); a = ap.parse_args()
if a.score:
    rows = [r for r in csv.DictReader(open(a.csv, encoding="utf-8")) if r["ok"].strip().lower() in ("y", "n")]
    good = sum(r["ok"].strip().lower() == "y" for r in rows)
    print(f"{good}/{len(rows)} correct" + (f" = {100*good/len(rows):.0f}%" if rows else "")); raise SystemExit
nodes = {n["id"]: n for n in json.load(open(f"{a.graph}/nodes.json", encoding="utf-8"))}
ev = [e for e in json.load(open(f"{a.graph}/edges.json", encoding="utf-8")) if e["type"] in ("ATTACKED", "THREATENED")]
random.seed(1); pick = random.sample(ev, min(a.n, len(ev)))
w = csv.writer(open(a.csv, "w", newline="", encoding="utf-8")); w.writerow(["post_url", "claim", "type", "model_reason", "text", "ok"])
for e in pick:
    p = nodes[e["post"]]; w.writerow([p["url"], f'{e["source"][8:]} -> {e["target"][8:]}', e["type"], e.get("why", ""), p["snippet"], ""])
print(f"wrote {len(pick)} rows to {a.csv}: open each link, write y or n in column 'ok', then run with --score")
