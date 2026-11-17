"""Card data from Scryfall: Forge-compatible names, colour identity, types, oracle text."""
import json
import os
import threading
import urllib.parse

from .net import get_json, post_json

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
        return {"name": c["name"], "forge_name": forge_name, "layout": layout,
                "cmc": c.get("cmc", 0), "type_line": type_line, "oracle": oracle,
                "mana_cost": mana_cost, "color_identity": c.get("color_identity", []),
                "game_changer": bool(c.get("game_changer", False)),
                "legal_commander": (c.get("legalities", {}).get("commander") == "legal")}

    def get(self, name):
        return self.cards.get(self._key(name))

    def resolve(self, names):
        """Look up all names (cached). Returns list of names not found."""
        missing = sorted({n for n in names if self._key(n) not in self.cards})
        not_found = []
        for i in range(0, len(missing), 75):
            chunk = missing[i:i + 75]
            # Scryfall matches the front face of double-faced cards by name
            ids = [{"name": n.split(" // ")[0] if " // " in n else n} for n in chunk]
            res = post_json("https://api.scryfall.com/cards/collection", {"identifiers": ids})
            found = {}
            for c in res.get("data", []):
                info = self._info(c)
                for alias in {c["name"], info["forge_name"]} | {f["name"] for f in c.get("card_faces", [])}:
                    found[self._key(alias)] = info
            with self.lock:
                self.cards.update(found)
            for n in chunk:
                if self._key(n) not in self.cards and self._key(n.split(" // ")[0]) not in self.cards:
                    not_found.append(n)
                elif self._key(n) not in self.cards:
                    self.cards[self._key(n)] = self.cards[self._key(n.split(" // ")[0])]
        still = []
        for n in not_found:  # fuzzy fallback for typos / odd formatting
            c = get_json("https://api.scryfall.com/cards/named?fuzzy=" + urllib.parse.quote(n), host_gap=0.12)
            if c and c.get("object") == "card":
                with self.lock:
                    self.cards[self._key(n)] = self._info(c)
            else:
                still.append(n)
        if missing:
            self.save()
        return still
