"""Try an LLM on the hard posts in tools/probe_cases.json and compare with what we expect.

Uses GitHub Models (free, rate limited). Nothing is written to data/; this only prints.

  export GITHUB_TOKEN=...        # a fine-grained personal access token with "Models: read"
  python tools/llm_probe.py                      # all cases
  python tools/llm_probe.py --case 13930         # one case
  python tools/llm_probe.py --model openai/gpt-4.1-mini
  python tools/llm_probe.py --dry                # show the prompt, call nothing

Inside GitHub Actions the same code works with the built-in GITHUB_TOKEN if the job has `models: read`.
Only the standard library is used.
"""
import argparse, json, os, sys, time, urllib.request, urllib.error
from pathlib import Path

URL = "https://models.github.ai/inference/chat/completions"
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


def ask(text, model, token, tries=4):
    body = json.dumps({"model": model, "temperature": 0, "max_tokens": 600,
                       "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text[:1500]}]}).encode()
    for i in range(tries):
        req = urllib.request.Request(URL, data=body, method="POST", headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json",
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
                return data["choices"][0]["message"]["content"], data.get("usage", {})
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code == 429 and i < tries - 1:
                wait = int(e.headers.get("Retry-After", "20"))
                print(f"   rate limited, waiting {wait}s ...", file=sys.stderr)
                time.sleep(wait)
                continue
            sys.exit(f"HTTP {e.code} from GitHub Models: {detail}\n"
                     "403/401 usually means the token lacks 'Models: read' (or the model id is wrong).")
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
    return miss, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="openai/gpt-4.1")
    ap.add_argument("--case", type=int)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    cases = [c for c in json.load(open(CASES, encoding="utf-8")) if not a.case or c["id"] == a.case]
    if a.dry:
        print(SYSTEM)
        print("--- first case ---")
        print(cases[0]["text"])
        return
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("Set GITHUB_TOKEN (fine-grained personal access token with 'Models: read').")
    ok = 0
    for c in cases:
        raw, usage = ask(c["text"], a.model, token)
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
    print(f"\n{ok}/{len(cases)} cases passed with {a.model}")


if __name__ == "__main__":
    main()
