"""Turn the stored LLM result of a post into map arrows. Pure functions: no geo libraries, easy to test.

An arrow is [origin_lat, origin_lon, dest_lat, dest_lon, label, kind, attacker_iso], kind 'p' (physical) or 'v' (verbal).
A post can have several arrows; they all end near the place of the event.
"""


def visible(events):
    """Arrows worth drawing: those the extractor marked as shown, physical first, then by confidence."""
    ev = [e for e in events if e.get("show")]
    return sorted(ev, key=lambda e: (e["kind"] != "physical", -e["confidence"]))


def plan(events, pt, place=None):
    """Work out coordinates for each arrow.

    events: visible events (dicts with from/to/kind). pt: {iso: (lat, lon)}.
    place: (lat, lon, iso, conf) of a precisely found place in the post, or None.
    An event whose "to" is None is drawn to the exact place (needs `place`); it is marked "open": True.
    Returns (arrows, skipped): arrows are dicts with from, to, kind, org, dest, conf ('p' = exact place, 'a' = country area), open;
    skipped lists events dropped because a country has no known coordinates.
    """
    out, skipped = [], []
    for e in events:
        a, b = e["from"], e["to"]
        is_open = b is None                                     # attacker named, no target country (ship at sea, ...)
        if is_open:
            if a not in pt or not place:
                skipped.append(e)
                continue
            b = place[2]                                        # the country the named place lies in, only used for colours and filters
            dest, conf = (place[0], place[1]), "p"
        elif a not in pt or (b not in pt and not (place and place[2] == b)):
            skipped.append(e)
            continue
        elif place and place[2] == b:
            dest, conf = (place[0], place[1]), "p"
        else:
            dest, conf = pt[b], "a"
        out.append({"from": a, "to": b, "kind": "v" if e["kind"] == "verbal" else "p", "org": pt[a], "dest": dest, "conf": conf,
                    "open": is_open})
    return out, skipped


def main_first(arrows, loc):
    """Arrows that end in the event's own country come first: the dot, the colour side and the panel start with them."""
    return sorted(arrows, key=lambda a: a["to"] != loc)      # sorted() is stable, so the other order is kept


def unique(seq):
    seen = set()
    return [x for x in seq if not (x in seen or seen.add(x))]


def country_ids(arrows, mentioned, ids, location=None):
    """(attacker ids, involved ids) for the page filters.

    attacker ids keep the order of the arrows (the page uses the first one to colour by side).
    involved ids: the targets first (the first one is the post's main country), then the location, then every other country mentioned.
    """
    att = unique(i for a in arrows for i in ids(a["from"]))
    inv = unique([i for a in arrows for i in ids(a["to"])] + (ids(location) if location else []) +
                 [i for c in mentioned for i in ids(c)])
    return att, inv
