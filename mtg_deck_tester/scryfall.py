"""Card data from Scryfall: Forge-compatible names, colour identity, types, oracle text."""
import json
import os
import threading
import time
import urllib.parse

from .net import blocked_for, get_json, post_json

CACHE_VERSION = 2
USD_TO_EUR = 0.9  # rough fallback when a card has no Cardmarket price
PRICE_MAX_AGE = 7 * 24 * 3600  # prices are refreshed weekly
FRONT_FACE_LAYOUTS = {"transform", "modal_dfc", "adventure", "flip", "meld",
                      "reversible_card", "prepare"}


class CardDB:
    def __init__(self, cache_path):
        self.cache_path = cache_path
        self.lock = threading.Lock()
        self.cards = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, encoding="utf-8") as f:
                    self.cards = json.load(f)
            except Exception:
                self.cards = {}

    def save(self):
        with self.lock:
            tmp = self.cache_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.cards, f)
            os.replace(tmp, self.cache_path)

    @staticmethod
    def _key(name):
        return name.strip().lower()

    @staticmethod
    def _info(c):
        faces = c.get("card_faces") or []
        layout = c.get("layout", "normal")
        if faces and layout in FRONT_FACE_LAYOUTS:
            forge_name = faces[0]["name"]
        else:
            forge_name = c["name"]
        oracle = c.get("oracle_text") or " // ".join(f.get("oracle_text", "") for f in faces)
        type_line = c.get("type_line") or " // ".join(f.get("type_line", "") for f in faces)
        mana_cost = c.get("mana_cost") or (faces[0].get("mana_cost", "") if faces else "")
        prices = c.get("prices") or {}

        def num(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        power = c.get("power") or (faces[0].get("power") if faces else None)
        return {"name": c["name"], "forge_name": forge_name, "layout": layout,
                "cmc": c.get("cmc", 0), "type_line": type_line, "oracle": oracle,
                "mana_cost": mana_cost, "color_identity": c.get("color_identity", []),
                "game_changer": bool(c.get("game_changer", False)),
                "legal_commander": (c.get("legalities", {}).get("commander") == "legal"),
                "power": power, "keywords": c.get("keywords") or [],
                "eur": num(prices.get("eur")), "usd": num(prices.get("usd")),
                "scryfall_uri": c.get("scryfall_uri", ""), "v": CACHE_VERSION, "fetched": int(time.time())}

    def get(self, name):
        return self.cards.get(self._key(name))

    def _fresh(self, key):
        e = self.cards.get(key)
        return bool(e) and e.get("v") == CACHE_VERSION and time.time() - e.get("fetched", 0) < PRICE_MAX_AGE

    def price(self, name):
        """Price in EUR of the cheapest paper printing (Cardmarket trend via Scryfall) when it has been looked
        up, otherwise of Scryfall's default printing. Falls back to USD converted roughly. None if unknown."""
        e = self.get(name)
        if not e:
            return None
        fresh_min = time.time() - e.get("min_fetched", 0) < PRICE_MAX_AGE
        for k in (("eur_min", "eur") if fresh_min else ("eur",)):
            if e.get(k) is not None:
                return e[k]
        for k in (("usd_min", "usd") if fresh_min else ("usd",)):
            if e.get(k) is not None:
                return round(e[k] * USD_TO_EUR, 2)
        return None

    def cheapest(self, names, min_price=1.0, log=None, label=""):
        """Look up the cheapest paper printing of every card whose standard printing costs at least
        min_price (or has no price). About 12 cards share one Scryfall search, Scryfall's limit of
        2 searches per second is respected, and results are cached for a week."""
        todo = []
        for n in dict.fromkeys(names):
            e = self.get(n)
            if not e or time.time() - e.get("min_fetched", 0) < PRICE_MAX_AGE:
                continue
            if e.get("type_line", "").startswith("Basic Land"):
                continue
            p = e.get("eur") if e.get("eur") is not None else e.get("usd")
            if p is None or p >= min_price:
                todo.append(n)
        if not todo:
            return
        if log:
            log(f"Looking up the cheapest printing of {len(todo)} card(s){label}...")
        changed = False
        for start in range(0, len(todo), 12):
            if blocked_for("api.scryfall.com"):
                if log:
                    log("Scryfall asked for a pause; using standard printings for the remaining prices.")
                break
            batch = todo[start:start + 12]
            fronts = {}
            for n in batch:
                fronts[self.get(n)["name"].split(" // ")[0].lower()] = n
            q = "(" + " or ".join(f'!"{f}"' for f in {self.get(n)["name"].split(" // ")[0] for n in batch}) + \
                ") game:paper -set_type:memorabilia -is:oversized"
            url = ("https://api.scryfall.com/cards/search?unique=prints&order=eur&dir=asc&q="
                   + urllib.parse.quote(q))
            best = {}
            pages = 0
            while url and pages < 8:
                try:
                    data = get_json(url, retries=1)
                except Exception:
                    data = None
                if not data:
                    break
                for c in data.get("data", []):
                    key = c.get("name", "").split(" // ")[0].lower()
                    if key not in fronts:
                        continue
                    pr = c.get("prices") or {}
                    b = best.setdefault(key, {"eur": [], "usd": []})
                    for k in ("eur", "usd"):
                        try:
                            if pr.get(k) is not None:
                                b[k].append(float(pr[k]))
                        except (TypeError, ValueError):
                            pass
                url = data.get("next_page") if data.get("has_more") else None
                pages += 1
            with self.lock:
                for key, n in fronts.items():
                    e = self.get(n)
                    b = best.get(key)
                    if b is None:
                        continue  # not found: keep the standard printing's price
                    e["eur_min"] = min(b["eur"]) if b["eur"] else None
                    e["usd_min"] = min(b["usd"]) if b["usd"] else None
                    e["min_fetched"] = int(time.time())
                    changed = True
        if changed:
            self.save()

    def resolve(self, names):
        """Look up card data for all names (cached for a week). Returns the names Scryfall doesn't know."""
        missing = sorted({n for n in names if n and not self._fresh(self._key(n))})
        not_found = []
        for i in range(0, len(missing), 75):  # the collection endpoint takes 75 cards per request
            chunk = missing[i:i + 75]
            # Scryfall matches the front face of double-faced cards by name
            ids = [{"name": n.split(" // ")[0] if " // " in n else n} for n in chunk]
            res = post_json("https://api.scryfall.com/cards/collection", {"identifiers": ids}, host_gap=0.6)
            found = {}
            for c in res.get("data", []):
                info = self._info(c)
                for alias in {c["name"], info["forge_name"]} | {f["name"] for f in c.get("card_faces", [])}:
                    found[self._key(alias)] = info
            with self.lock:
                self.cards.update(found)
            for n in chunk:
                if not self._fresh(self._key(n)) and not self._fresh(self._key(n.split(" // ")[0])):
                    not_found.append(n)
                elif not self._fresh(self._key(n)):
                    self.cards[self._key(n)] = self.cards[self._key(n.split(" // ")[0])]
        still = []
        for n in not_found:  # fuzzy fallback for typos / odd formatting (2 requests per second)
            if blocked_for("api.scryfall.com"):
                still.append(n)
                continue
            try:
                c = get_json("https://api.scryfall.com/cards/named?fuzzy=" + urllib.parse.quote(n), host_gap=0.6)
            except Exception:
                c = None
            if c and c.get("object") == "card":
                with self.lock:
                    self.cards[self._key(n)] = self._info(c)
            else:
                still.append(n)
        if missing:
            self.save()
        return still

def deck_value(deck, card_db):
    """(total EUR, number of cards without a price)."""
    total, unknown = 0.0, 0
    for q, n in [(1, c) for c in deck.commanders] + list(deck.cards):
        p = card_db.price(n) if card_db else None
        if p is None:
            unknown += q
        else:
            total += p * q
    return round(total, 2), unknown
