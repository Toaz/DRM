"""Shrink a Telegram Desktop export (52 MB for this channel) into the smaller data/result_old.json.

    python tools/slim.py path/to/result.json
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from common import DATA, txt

d = json.load(open(sys.argv[1], encoding="utf-8"))
out = [{"id": m["id"], "type": "message", "date": m["date"], "date_unixtime": m.get("date_unixtime", ""), "text": txt(m)}
       for m in d["messages"] if m.get("type") == "message" and txt(m).strip()]
json.dump({"name": d.get("name", "De Re Militari"), "messages": out}, open(DATA / "result_old.json", "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))
print(len(out), "posts written to data/result_old.json")
