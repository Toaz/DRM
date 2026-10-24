"""Try an LLM on the hard posts in tools/probe_cases.json and compare with what we expect.

The prompt, the API call and the arrow guards live in src/extract.py; this tool only tests them.
Works with any OpenAI-compatible chat API. Presets: groq, gemini, openrouter. Nothing is written to data/.

  export GROQ_API_KEY=...                         # or GEMINI_API_KEY / OPENROUTER_API_KEY
  python3 tools/llm_probe.py --provider groq --case 13930     # one post, tests the connection
  python3 tools/llm_probe.py --provider groq                  # all cases
  python3 tools/llm_probe.py --provider groq --sample 30      # random recent posts, model vs current rules, for you to judge
  python3 tools/llm_probe.py --provider gemini --model <name from Google AI Studio>
  python3 tools/llm_probe.py --dry                            # show the prompt, call nothing
"""
import argparse, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import extract
from extract import SYSTEM, PROVIDERS, parse, clean_events

CASES = Path(__file__).with_name("probe_cases.json")


def ask(text, model, token, base_url):
    """Same call as the real pipeline, but a failure ends the probe with a readable message."""
    try:
        return extract.ask(text, model, token, base_url), {}
    except extract.LLMError as e:
        sys.exit(str(e))


def score(case, out):
    ev = [e for e in clean_events(out) if e["show"]]
    phys = {(e["from"], e["to"]) for e in ev if e["kind"] == "physical"}
    anyk = {(e["from"], e["to"]) for e in ev}
    miss = [f"{a}->{b}" for a, b in case.get("required", []) if (a, b) not in phys]
    bad = [f"{a}->{b}" for a, b in case.get("forbidden", []) if (a, b) in anyk]
    bad += [f"{a}->{b} (physical)" for a, b in case.get("forbidden_physical", []) if (a, b) in phys]
    if "max_events" in case and len(ev) > case["max_events"]:
        bad.append(f"{len(ev)} arrows shown, expected at most {case['max_events']}")
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
        ev = "; ".join(f"{e['from']}->{e['to']} ({e['kind'][0]}, {e['confidence']}{'' if e['show'] else ', hidden'})" for e in clean_events(out)) or "none"
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
        print("   model         : " + ("; ".join(f"{e['from']}->{e['to']} ({e['kind']}, {e['confidence']}{'' if e['show'] else ', HIDDEN'}) {e['why']}"
                                           for e in clean_events(out)) or "no events"))
        print(f"   location={out.get('location')}  category={out.get('category')}  countries={out.get('countries')}")
        if miss:
            print("   MISSING:", ", ".join(miss))
        if bad:
            print("   WRONG  :", ", ".join(bad))
        time.sleep(1)
    print(f"\n{ok}/{len(cases)} cases passed with {a.provider}/{model}")


if __name__ == "__main__":
    main()
