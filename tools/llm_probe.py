"""Try an LLM on the hard posts in tools/probe_cases.json and compare with what we expect.

Works with any OpenAI-compatible chat API. Presets: groq, gemini, openrouter. Nothing is written to data/.

  export GROQ_API_KEY=...                         # or GEMINI_API_KEY / OPENROUTER_API_KEY
  python3 tools/llm_probe.py --provider groq --case 13930     # one post, tests the connection
  python3 tools/llm_probe.py --provider groq                  # all cases
  python3 tools/llm_probe.py --provider gemini --model <name from Google AI Studio>
  python3 tools/llm_probe.py --provider openrouter --model <a model id ending in :free>
  python3 tools/llm_probe.py --provider groq --sample 30      # random recent posts, model vs current rules, for you to judge
  python3 tools/llm_probe.py --dry                            # show the prompt, call nothing

Only the standard library is used.
"""
import argparse, json, os, sys, time, urllib.request, urllib.error
from pathlib import Path

PROVIDERS = {  # base url, env var holding the key, default model (None = must pass --model)
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "openai/gpt-oss-120b"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "gemini-flash-latest"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", None),
}
CASES = Path(__file__).with_name("probe_cases.json")
CATS = "war mil dip sea eng hum sec nuc air cyb ter pro dis arm avi gen"

SYSTEM = f"""You read short news posts (mostly Bulgarian) from a military/geopolitics channel and extract structured data for a map.
Answer with ONE JSON object and nothing else (no markdown fences):
{{"countries": [ISO codes of every country or bloc the post is about],
  "location": ISO code of the country where the main event happens, or null,
  "category": one of: {CATS},
  "events": [{{"from": ISO, "to": ISO, "kind": "physical" or "verbal", "confidence": 0.0-1.0, "why": "max 12 words"}}]}}

Rules for "events" (these become arrows on the map, from attacker to victim):
- One event per attacker->victim pair. Several attackers or several victims means several events. Two-way exchanges give two events.
- "physical": strikes, shelling, drone/missile attacks, invasions, shoot-downs, sabotage by a state or its forces.
- "verbal": threats, ultimatums, sanctions, accusations, condemnations aimed at a country.
- The FROM country is whoever carries out the act, the TO country is whoever suffers it. Read passive sentences carefully
  ("X was struck by Y" means Y->X). Shooting down an incoming drone is defence: the drone's owner is the attacker.
- Armed groups map to the country they operate from (Hamas -> PS, Hezbollah -> LB, Houthis -> YE).
- Countries that only help, supply, host, comment or negotiate are NOT attackers. Deliveries, aid, talks, deployments, exercises,
  economic news and background mentions produce no event.
- If the post only mentions an attack as the reason for something else, still list it but lower the confidence.
- Use ISO 3166-1 alpha-2 codes, plus EU and UN. If there is no event, return "events": [].
"""


def ask(text, model, token, base_url, tries=4):
    body = json.dumps({"model": model, "temperature": 0, "max_tokens": 2000,
                       "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text[:1500]}]}).encode()
    for i in range(tries):
        req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body, method="POST", headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": "drm-map-probe"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                status, ctype, final = r.status, r.headers.get("Content-Type"), r.geturl()
                payload = r.read().decode("utf-8", "replace")
            try:
                data = json.loads(payload)
                content = data["choices"][0]["message"]["content"]
                if not content:
                    raise ValueError("empty content")
                return content, data.get("usage", {})
            except (ValueError, KeyError, IndexError, TypeError):
                sys.exit("The API answered, but not with a usable result.\n"
                         f"  status      : {status}\n  content-type: {ctype}\n  url         : {final}\n"
                         f"  body (first 500 chars): {payload[:500]!r}\n"
                         "Please send me this block (it contains no token).")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code == 429 and i < tries - 1:
                wait = int(e.headers.get("Retry-After", "20"))
                print(f"   rate limited, waiting {wait}s ...", file=sys.stderr)
                time.sleep(wait)
                continue
            sys.exit(f"HTTP {e.code} from {base_url}: {detail}\n"
                     "401/403 usually means a wrong or missing key; 404 or 400 often means the model name is wrong.")
    sys.exit("Gave up after repeated rate limits.")


def parse(raw):
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("{"):]
    return json.loads(s[s.find("{"): s.rfind("}") + 1])


def score(case, out):
    ev = out.get("events", [])
    phys = {(e["from"], e["to"]) for e in ev if e.get("kind") == "physical"}
    anyk = {(e["from"], e["to"]) for e in ev}
    miss = [f"{a}->{b}" for a, b in case["required"] if (a, b) not in phys]
    bad = [f"{a}->{b}" for a, b in case["forbidden"] if (a, b) in anyk]
    bad += [f"{a}->{b} (physical)" for a, b in case.get("forbidden_physical", []) if (a, b) in phys]
    return miss, bad


def rules_arrow(text):
    """What the current rule-based code says (needs the project's requirements installed)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        import place
        t = " ".join(text.split())
        loc = place.locate(t)
        d = place.detect(t, loc[2] if loc else None)
        return f"{d[0]}->{d[1][2]}" if d else "none"
    except Exception as e:  # missing packages, different layout, ...
        return f"n/a ({type(e).__name__})"


def run_sample(a, model, token, base_url):
    import random
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from common import load_all, txt
    posts = [m for m in load_all() if m["date"] >= a.since and len(txt(m).strip()) > 60]
    random.Random(a.seed).shuffle(posts)
    print(f"{len(posts)} posts since {a.since}; judging {min(a.sample, len(posts))} random ones (seed {a.seed})\n")
    for m in posts[: a.sample]:
        t = txt(m).strip()
        raw, _ = ask(t, model, token, base_url)
        try:
            out = parse(raw)
        except ValueError:
            out = {"events": [], "location": "?"}
        ev = "; ".join(f"{e['from']}->{e['to']} ({e['kind'][0]}, {e.get('confidence', '?')})" for e in out.get("events", [])) or "none"
        print(f"#{m['id']} {m['date'][:10]}  {' '.join(t.split())[:230]}")
        print(f"   rules: {rules_arrow(t)}")
        print(f"   model: {ev}   [location={out.get('location')}]\n")
        time.sleep(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=sorted(PROVIDERS), default="groq")
    ap.add_argument("--model")
    ap.add_argument("--case", type=int)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--sample", type=int, help="judge N random recent posts instead of the fixed cases")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--since", default="2026-01-01")
    a = ap.parse_args()
    cases = [c for c in json.load(open(CASES, encoding="utf-8")) if not a.case or c["id"] == a.case]
    if a.dry:
        print(SYSTEM)
        print("--- first case ---")
        print(cases[0]["text"])
        return
    base_url, env, default_model = PROVIDERS[a.provider]
    model = a.model or default_model
    if not model:
        sys.exit(f"{a.provider} has no default model; pass --model <id>.")
    token = os.environ.get(env)
    if not token:
        sys.exit(f"Set {env} first, e.g.  export {env}=...")
    if a.sample:
        return run_sample(a, model, token, base_url)
    ok = 0
    for c in cases:
        raw, usage = ask(c["text"], model, token, base_url)
        try:
            out = parse(raw)
        except ValueError:
            print(f"#{c['id']}  UNPARSEABLE ANSWER: {raw[:200]!r}")
            continue
        miss, bad = score(c, out)
        good = not miss and not bad
        ok += good
        print(f"#{c['id']} {'PASS' if good else 'FAIL'}  {c['note']}")
        print(f"   current rules : {c['rules_said']}")
        print("   model         : " + ("; ".join(f"{e['from']}->{e['to']} ({e['kind']}, {e.get('confidence', '?')}) {e.get('why', '')}"
                                           for e in out.get("events", [])) or "no events"))
        print(f"   location={out.get('location')}  category={out.get('category')}  countries={out.get('countries')}")
        if miss:
            print("   MISSING:", ", ".join(miss))
        if bad:
            print("   WRONG  :", ", ".join(bad))
        time.sleep(1)
    print(f"\n{ok}/{len(cases)} cases passed with {a.provider}/{model}")


if __name__ == "__main__":
    main()
