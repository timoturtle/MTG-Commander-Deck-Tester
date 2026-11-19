"""What other players run with your commander, from EDHREC (https://edhrec.com).

EDHREC has no official API. This reads the public JSON its website loads
(json.edhrec.com/pages/commanders/<slug>.json), slowly and cached for a week. EDHREC changes
that format from time to time, so every field is read defensively and failures are reported,
not fatal.
"""
import json
import os
import re
import time
import unicodedata

from .net import get_json

BASE = "https://json.edhrec.com/pages/commanders/{}.json"
MAX_AGE = 7 * 24 * 3600


def slug(name):
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.split(" // ")[0].lower()
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    return re.sub(r"[\s-]+", "-", name).strip("-")


def _slugs(commanders):
    s = [slug(c) for c in commanders]
    if len(s) == 1:
        return s
    return ["-".join(sorted(s)), "-".join(s), "-".join(reversed(s)), s[0]]


class Edhrec:
    def __init__(self, cache_dir, log=print):
        self.cache_dir = os.path.join(cache_dir, "edhrec")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.log = log

    def _page(self, sl):
        path = os.path.join(self.cache_dir, sl + ".json")
        if os.path.exists(path) and time.time() - os.path.getmtime(path) < MAX_AGE:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        data = get_json(BASE.format(sl), host_gap=1.2)
        if data:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        return data

    def commander_cards(self, commanders):
        """{'url', 'decks', 'cards': {name: {'inclusion': 0-100, 'synergy': -1..1, 'list': header}}} or None."""
        for sl in _slugs(commanders):
            try:
                data = self._page(sl)
            except Exception as e:
                self.log(f"EDHREC unavailable: {e}")
                return None
            if not data:
                continue
            container = (data.get("container") or {}).get("json_dict") or {}
            cards = {}
            for cl in container.get("cardlists") or []:
                header = cl.get("header") or cl.get("tag") or ""
                for cv in cl.get("cardviews") or []:
                    name = cv.get("name")
                    if not name:
                        continue
                    num = cv.get("num_decks", cv.get("inclusion"))
                    pot = cv.get("potential_decks")
                    incl = round(100 * num / pot, 1) if isinstance(num, (int, float)) and pot else None
                    syn = cv.get("synergy", cv.get("lift"))
                    old = cards.get(name)
                    if old is None or (incl or 0) > (old["inclusion"] or 0):
                        cards[name] = {"inclusion": incl, "synergy": syn if isinstance(syn, (int, float)) else None,
                                       "list": header}
            if not cards:
                self.log("EDHREC: the page format wasn't recognised; skipping the comparison.")
                return None
            decks = data.get("num_decks_avg") or data.get("num_decks") or \
                (container.get("card") or {}).get("num_decks")
            return {"url": f"https://edhrec.com/commanders/{sl}", "decks": decks, "cards": cards}
        self.log("EDHREC has no page for this commander.")
        return None
