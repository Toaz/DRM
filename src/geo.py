"""Turn the place name the model found ("Kharkiv") into coordinates, using the city list that geonamescache ships.

Pure functions plus one small class: no network, and the city list is passed in, so the tests use a tiny fake one.

The rule that keeps it safe: a name is only accepted inside a country we already believe in (the post's location or the
target of an arrow). "Paris" with no hint is refused when there are several Parises. A name that is not found simply
returns None and the caller keeps using what it had before.
"""
import re, unicodedata

# words that only say what kind of place it is ("Samara Oblast" -> "samara")
_NOISE = {"oblast", "region", "province", "city", "district", "governorate", "krai", "raion", "municipality", "of", "the"}


def norm(name):
    """Lower case, no accents, only letters and digits, generic words dropped: 'Dnipró Oblast' -> 'dnipro'."""
    s = unicodedata.normalize("NFKD", str(name)).casefold()
    s = "".join(c for c in s if not unicodedata.combining(c))
    words = [w for w in re.split(r"[^\w]+", s) if w and w not in _NOISE]
    return " ".join(words)


class Gazetteer:
    """Index of cities by every name they are known under.  `cities`: dicts with the geonamescache keys
    name, alternatenames, countrycode, latitude, longitude, population."""

    def __init__(self, cities):
        self.by_name = {}
        for c in cities:
            entry = (int(c.get("population") or 0), c["countrycode"], float(c["latitude"]), float(c["longitude"]))
            for n in {norm(c["name"])} | {norm(a) for a in c.get("alternatenames", []) if isinstance(a, str)}:
                if n:
                    self.by_name.setdefault(n, []).append(entry)

    def find(self, name, country=None):
        """-> (lat, lon, iso) or None.  With `country`: the biggest city of that name there.  Without: only if the name is unique."""
        hits = self.by_name.get(norm(name), [])
        if country:
            hits = [h for h in hits if h[1] == country]
            if not hits:
                return None
            best = max(hits)
            return best[2], best[3], best[1]
        if len(hits) == 1:
            return hits[0][2], hits[0][3], hits[0][1]
        return None


def place_for(rec, gaz):
    """Coordinates for the place the model named in record `rec`: (lat, lon, iso, 'p') or None.

    Countries tried, in order: the post's location, then the target of each arrow. The first country that has a city of
    that name wins; with no country at all the name must be unique in the whole list.
    """
    name = rec.get("pl")
    if not name:
        return None
    hints = []
    for c in [rec.get("loc")] + [e.get("to") for e in rec.get("ev", [])]:
        if c and c not in hints and c not in ("EU", "UN"):
            hints.append(c)
    for c in hints or [None]:
        hit = gaz.find(name, c)
        if hit:
            return hit[0], hit[1], hit[2], "p"
    return None


def km(a, b):
    """Rough distance in km between two (lat, lon) points (equirectangular, good enough for 'are these the same place')."""
    import math
    dy = (a[0] - b[0]) * 111.0
    dx = (a[1] - b[1]) * 111.0 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dx, dy)
