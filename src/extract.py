"""Read each post once with an LLM and store what it found: countries, location, category and attack arrows.

The result goes to data/events.json (one line per post, easy to diff in git). A post is only sent to the model if it
has no record yet or its text changed, so old results never change when the prompt is edited. Posts without a record
simply keep using the old rule-based code in place.py.

  export GROQ_API_KEY=...                 # free key from console.groq.com (or GEMINI_API_KEY / OPENROUTER_API_KEY)
  python src/extract.py --dry             # how many posts are waiting
  python src/extract.py --limit 5         # try it on the 5 newest waiting posts
  python src/extract.py --since 2026-01-01   # leave older posts to the old rules (or set EXTRACT_SINCE)
  python src/extract.py --redo 20152      # read one post again
  python src/extract.py --redo-stale --limit 90   # re-read posts made with an older prompt (e.g. to add the new "place" field)
  python src/extract.py                   # normal run (EXTRACT_LIMIT or 30 posts, newest first)

Without an API key the script prints a note and exits normally, so the daily workflow never fails because of it.
Only the standard library is used.
"""
import os, sys, json, time, hashlib, argparse, urllib.request, urllib.error
from common import DATA, load_all, txt

CACHE = DATA / "events.json"
PROVIDERS = {  # base url, env var holding the key, default model (None = must set LLM_MODEL)
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "openai/gpt-oss-120b"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "gemini-flash-latest"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", None),
}
CATS = "war mil dip sea eng hum sec nuc air cyb ter pro dis arm avi gen"
SYSTEM = f"""You read short news posts (mostly Bulgarian) from a military/geopolitics channel and extract structured data for a map.
Answer with ONE JSON object and nothing else (no markdown fences):
{{"countries": [ISO codes of every country or bloc the post is about],
  "location": ISO code of the country where the main event happens, or null,
  "place": the most specific named city, town, region or facility where the event happens, in English, or null,
  "category": one of: {CATS},
  "events": [{{"from": ISO, "to": ISO, "kind": "physical" or "verbal", "confidence": 0.0-1.0, "why": "max 12 words"}}]}}

Rules for "events" (these become arrows on the map, from attacker to victim):
- One event per attacker->victim pair. Several attackers or several victims means several events. Two-way exchanges give two events.
- "physical": strikes, shelling, drone/missile attacks, invasions, incursions, shoot-downs, sabotage by a state or its forces.
- "verbal": ONLY an explicit threat, ultimatum, formal accusation, sanction or condemnation by a government or bloc aimed at a named state.
  Court rulings, flight or airspace closures, summit announcements, statements about talks and trade news are NOT events.
- The FROM country is whoever carries out the act, the TO country is whoever suffers it. FROM and TO must be different countries.
  Read passive sentences carefully ("X was struck by Y" means Y->X). Shooting down an incoming drone is defence: the drone's owner is the attacker.
- Do NOT guess who did it. If the post does not state or clearly imply the attacker, return no event for it.
  Flags and hashtags at the start of a post only say which countries are involved, they do not say who attacked whom.
- For ships and other assets, TO is the state whose territory, forces or owner/operator was hit, NEVER the ship's flag state. If unclear, use null.
  When the attacker is named but the victim has no clear state (a ship at sea), still return the event with "to": null. Never leave it out.
- Armed groups map to the country they operate from (Hamas -> PS, Hezbollah -> LB, Houthis -> YE).
- Countries that only help, supply, host, comment or negotiate are NOT attackers. Deliveries, aid, talks, prisoner releases, hostage deals,
  deployments, exercises, court cases and economic news produce no event.
- Plans, rumours, hypothetical operations and attacks mentioned only as the reason for something else: confidence 0.5 or lower.
- Use ISO 3166-1 alpha-2 codes, plus EU and UN. "location" must be a country code or null (never EU or UN). If there is no event, return "events": [].

Rules for "place": the name as a map would write it in English or in the usual transliteration ("Kharkiv", "Tolyatti", "Sanaa"),
without the word "oblast"/"region". Only a settlement, region or named facility that the post itself names; null when only a country is named.
Never guess a place the post does not mention. Several places: the one where the main effect happens.

Rules for "location" and "category":
- "location" is where the EFFECT happens, i.e. where the struck target is, NOT where the attacker comes from. A Ukrainian strike on a plant
  in Samara oblast has location RU. Russian oblasts, cities and facilities are RU, Ukrainian ones are UA, even if the post names no country there.
- A named place or facility inside a country makes that country the TO of the event, unless the post says otherwise.
  Flags at the start of a post list the countries involved; the target is the one where the named place lies.
- "category" is the kind of event, not the industry. Any strike, drone or missile attack on a refinery, plant, depot or other facility is "war".
  Use "eng" only for prices, sanctions, supplies and market news.

Examples (different posts, only to show the format and the traps):
Post: "A Liberian-flagged tanker was hit by a Houthi missile in the Red Sea, two crew injured."
{{"countries": ["YE", "LR"], "location": null, "place": "Red Sea", "category": "sea", "events": [{{"from": "YE", "to": null, "kind": "physical", "confidence": 0.9, "why": "Houthi missile hit tanker; flag state is not the victim"}}]}}
Post: "Egyptian airports suspended all flights to and from Libya."
{{"countries": ["EG", "LY"], "location": "EG", "place": null, "category": "avi", "events": []}}
Post: "France and Germany will send air defence to Ukraine. Russia launched 40 drones at Kharkiv overnight."
{{"countries": ["FR", "DE", "UA", "RU"], "location": "UA", "place": "Kharkiv", "category": "war", "events": [{{"from": "RU", "to": "UA", "kind": "physical", "confidence": 1.0, "why": "drone attack on Kharkiv"}}]}}
Post: "Ukraine struck the Tolyattikauchuk petrochemical plant in Samara oblast."
{{"countries": ["UA", "RU"], "location": "RU", "place": "Tolyatti", "category": "war", "events": [{{"from": "UA", "to": "RU", "kind": "physical", "confidence": 0.95, "why": "strike on plant in Samara oblast"}}]}}
"""
PROMPT_VERSION = hashlib.sha1(SYSTEM.encode()).hexdigest()[:8]
SHOW_PHYSICAL, SHOW_VERBAL = 0.7, 0.9  # below these an arrow stays in the data but is hidden / goes to review
MAX_TEXT = 1500


class LLMError(Exception):
    """The API could not give an answer (network, bad key, bad model, ...)."""


class QuotaExceeded(LLMError):
    """Daily or per-minute quota used up for longer than we are willing to wait."""


def ask(text, model, token, base_url, tries=4, max_wait=90):
    body = json.dumps({"model": model, "temperature": 0, "max_tokens": 2000,
                       "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text[:MAX_TEXT]}]}).encode()
    last = "no attempt made"
    for i in range(tries):
        req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body, method="POST", headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": "drm-map-extract"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                payload = r.read().decode("utf-8", "replace")
            data = json.loads(payload)
            content = data["choices"][0]["message"]["content"]
            if not content:
                raise ValueError("empty content")
            return content
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code == 429:
                try:
                    wait = int(float(e.headers.get("Retry-After", "20")))
                except ValueError:
                    wait = 20
                if wait > max_wait:
                    raise QuotaExceeded(f"rate limit, retry in {wait}s: {detail}")
                last = f"HTTP 429, waited {wait}s"
                time.sleep(wait)
                continue
            if e.code >= 500:
                last = f"HTTP {e.code}"
                time.sleep(2 * (i + 1))
                continue
            raise LLMError(f"HTTP {e.code} from {base_url}: {detail} (401/403 = bad key, 400/404 = bad model name?)")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = f"network: {e}"
            time.sleep(2 * (i + 1))
        except (ValueError, KeyError, IndexError, TypeError) as e:
            last = f"unusable answer ({e})"
            time.sleep(1)
    raise LLMError(f"gave up after {tries} tries: {last}")


def parse(raw):
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("{"):]
    return json.loads(s[s.find("{"): s.rfind("}") + 1])


def iso_ok(x, allow_blocs=True):
    ok = isinstance(x, str) and len(x) == 2 and x.isalpha() and x.isupper()
    return ok and (allow_blocs or x not in ("EU", "UN"))


def with_show(events):
    for ev in events:
        ev["show"] = ev["confidence"] >= (SHOW_PHYSICAL if ev["kind"] == "physical" else SHOW_VERBAL)
    return events


def clean_events(out):
    """Guards on whatever the model returned: no self-arrows, no duplicates, no invented codes.

    A physical attack by a named country with no target country is kept with "to": None; the page draws it to the place named in the post."""
    loc = out.get("location") if iso_ok(out.get("location"), allow_blocs=False) else None
    best = {}
    for e in out.get("events", []) or []:
        if not isinstance(e, dict):
            continue
        a, b = e.get("from"), e.get("to") or (loc if loc not in (None, e.get("from")) else None)
        kind = e.get("kind")
        if not iso_ok(a) or a == b or kind not in ("physical", "verbal"):
            continue
        if b is None:
            if kind != "physical":
                continue           # an open target is only meaningful for a physical attack (ship at sea, ...)
        elif not iso_ok(b):
            continue
        try:
            conf = max(0.0, min(1.0, float(e.get("confidence", 0))))
        except (TypeError, ValueError):
            conf = 0.0
        ev = {"from": a, "to": b, "kind": e["kind"], "confidence": conf, "why": str(e.get("why", ""))[:120]}
        old = best.get((a, b))
        rank = lambda x: (x["kind"] == "physical", x["confidence"])  # prefer physical, then higher confidence
        if old is None or rank(ev) > rank(old):
            best[(a, b)] = ev
    return with_show(list(best.values()))


def clean_place(x):
    """The place name the model gave, or None if it is empty, a bare number or unreasonably long."""
    if not isinstance(x, str):
        return None
    x = " ".join(x.split())
    return x if 2 <= len(x) <= 80 and not x.isdigit() and x.lower() not in ("null", "none", "n/a", "unknown") else None


def record(raw, text, model):
    """What we store for one post."""
    out = parse(raw)
    cats = CATS.split()
    rec = {"h": text_hash(text), "pv": PROMPT_VERSION, "m": model,
           "c": sorted({c for c in out.get("countries", []) if iso_ok(c)}),
           "loc": out.get("location") if iso_ok(out.get("location"), allow_blocs=False) else None,
           "cat": out.get("category") if out.get("category") in cats else None,
           "ev": [{k: v for k, v in e.items() if k != "show"} for e in clean_events(out)]}
    pl = clean_place(out.get("place"))
    if pl:
        rec["pl"] = pl                 # only stored when there is one, so old and new records stay equally small
    return rec


def text_hash(text):
    return hashlib.sha1(" ".join(text.split()).encode("utf-8")).hexdigest()[:12]


def load_cache(path=CACHE):
    if not path.exists():
        return {"version": 1, "posts": {}}
    with open(path, encoding="utf-8") as f:
        c = json.load(f)
    c.setdefault("posts", {})
    return c


def save_cache(cache, path=CACHE):
    """One post per line, written atomically: a failed run can never leave a half-written file."""
    lines = ",\n".join(f"{json.dumps(str(k))}:{json.dumps(v, ensure_ascii=False, separators=(',', ':'))}"
                       for k, v in sorted(cache["posts"].items(), key=lambda kv: int(kv[0])))
    tmp = path.with_suffix(".tmp")
    tmp.write_text('{"version":1,"posts":{\n' + lines + "\n}}\n", encoding="utf-8")
    os.replace(tmp, path)


def is_stale(rec):
    """Read with a different prompt than the current one."""
    return rec.get("pv") != PROMPT_VERSION


def waiting(posts, cache, stale=False, force=()):
    """Posts that still need the model, newest first.

    A post waits when it has no record, or its text was edited, or (only with stale=True) its record was made with an
    older prompt, or its id is in `force`. The old record stays in the cache until the new answer has arrived, so a
    failed or interrupted run loses nothing.
    """
    out = []
    force = {str(i) for i in force}
    for m in sorted(posts, key=lambda m: m["id"], reverse=True):
        t = txt(m).strip()
        if len(t) <= 20:
            continue
        old = cache["posts"].get(str(m["id"]))
        if (old is None or old.get("h") != text_hash(t) or str(m["id"]) in force
                or (stale and is_stale(old))):
            out.append(m)
    return out


def enrich(posts, cache, call, model, limit=30, sleep=1.0, save=None, save_every=10, stale=False, force=()):
    """Send up to `limit` waiting posts through `call(text) -> raw answer`. Stops quietly when the quota is used up."""
    st = {"done": 0, "unparseable": 0, "failed": 0, "quota": False}
    fails = 0
    for m in waiting(posts, cache, stale=stale, force=force)[:limit]:
        text = txt(m).strip()
        try:
            raw = call(text)
        except QuotaExceeded as e:
            st["quota"] = True
            print("quota used up, stopping for now:", e)
            break
        except LLMError as e:
            st["failed"] += 1
            fails += 1
            print(f"post {m['id']}: {e}")
            if fails >= 3:
                print("three failures in a row, stopping")
                break
            continue
        fails = 0
        try:
            cache["posts"][str(m["id"])] = record(raw, text, model)
        except ValueError:
            st["unparseable"] += 1           # not stored, so it is tried again next run
            print(f"post {m['id']}: answer was not valid JSON, skipped")
            continue
        st["done"] += 1
        if save and st["done"] % save_every == 0:
            save(cache)
        if sleep:
            time.sleep(sleep)
    if save:
        save(cache)
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=int(os.environ.get("EXTRACT_LIMIT", "30")))
    ap.add_argument("--dry", action="store_true", help="only count the posts that are waiting")
    ap.add_argument("--since", default=os.environ.get("EXTRACT_SINCE", ""), help="ignore posts older than this date, YYYY-MM-DD")
    ap.add_argument("--redo", type=int, nargs="+", metavar="ID", help="read these posts again, e.g. after a prompt change")
    ap.add_argument("--redo-stale", action="store_true", help="also read again the posts that were read with an older prompt (newest first, within --limit)")
    a = ap.parse_args()
    cache = load_cache()
    if a.redo:
        every = {m["id"]: m for m in load_all()}
        missing = [i for i in a.redo if i not in every]
        if missing:
            print("not found in the data:", missing)
        posts = [every[i] for i in a.redo if i in every]
        a.limit = max(a.limit, len(posts))            # the old records stay until the new answers arrive
    else:
        posts = [m for m in load_all() if m["date"][:10] >= a.since]
    force = [m["id"] for m in posts] if a.redo else ()
    todo = waiting(posts, cache, stale=a.redo_stale, force=force)
    old_prompt = sum(1 for r in cache["posts"].values() if is_stale(r))
    print(f"{len(cache['posts'])} posts analysed ({old_prompt} with an older prompt), {len(todo)} waiting")
    if a.dry or not todo:
        return
    provider = os.environ.get("LLM_PROVIDER", "groq")
    if provider not in PROVIDERS:
        sys.exit(f"LLM_PROVIDER must be one of {', '.join(PROVIDERS)}")
    base_url, env, default_model = PROVIDERS[provider]
    model = os.environ.get("LLM_MODEL") or default_model
    token = os.environ.get(env)
    if not token or not model:
        print(f"No {env if not token else 'LLM_MODEL'} set, skipping extraction (the old rules stay in use).")
        return
    st = enrich(posts, cache, lambda t: ask(t, model, token, base_url), f"{provider}/{model}", limit=a.limit, save=save_cache,
                stale=a.redo_stale, force=force)
    print(st, "| analysed now:", len(cache["posts"]))


if __name__ == "__main__":
    main()
