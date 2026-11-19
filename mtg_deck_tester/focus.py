"""Focus cards: everything the test shows about a few cards you're unsure about.

For each card it combines
* the Forge games: opening hands, every cast (turn, how often), damage it dealt, knock-outs, and how
  the games went with and without it
* the goldfish: how often the deck draws and casts it when playing on purpose
* combos it's part of (Commander Spellbook), EDHREC popularity with your commander, price, role
and turns that into a few plain observations. Nothing here is a verdict: with only a handful of games,
a card can look bad just because it wasn't drawn.
"""
from .analysis import classify
from .goldfish import norm

ROLE_WORDS = {"ramp": "ramp", "draw": "card draw", "removal": "removal", "wipe": "board wipe",
              "counter": "counterspell", "protection": "protection", "tutor": "tutor", "creature": "creature"}


def parse_focus(text):
    out = []
    for line in (text or "").replace(";", "\n").splitlines():
        name = line.strip().strip(",")
        if name and name.lower() not in {n.lower() for n in out}:
            out.append(name)
    return out[:10]


def match_names(focus, deck):
    """Map typed names to the deck's own card names (case-insensitive, either face of a double-faced card)."""
    by_key = {}
    for n in deck.all_names():
        by_key[n.lower()] = n
        by_key[norm(n)] = n
        if " // " in n:
            by_key[n.split(" // ")[1].strip().lower()] = n
    found, missing = [], []
    for f in focus:
        n = by_key.get(f.lower()) or by_key.get(norm(f))
        (found if n else missing).append(n or f)
    return list(dict.fromkeys(found)), missing


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


def analyze(names, deck, results, card_db, combo_data=None, edh=None):
    games = sorted([g for g in results["games"] if "D01" in g["players"]], key=lambda g: g["round"])
    deck_names = {n.lower() for n in deck.commanders}
    gf_focus = ((combo_data or {}).get("goldfish") or {}).get("focus") or {}
    edh_cards = (edh or {}).get("cards") or {}
    out = []
    for name in names:
        key = norm(name)
        info = card_db.get(name) if card_db else None
        is_cmd = name.lower() in deck_names
        rows, cast_games, first_turns, n_casts, dmg_c, dmg_n, kills = [], 0, [], 0, 0, 0, 0
        places_cast, places_not = [], []
        opening, opening_known = 0, 0
        for g in games:
            p = g["players"]["D01"]
            casts = [c for c in p.get("cast_log", []) if norm(c["card"]) == key]
            hand = p.get("opening_hand")
            in_hand = None
            if hand is not None and not is_cmd:  # a commander starts in the command zone
                opening_known += 1
                in_hand = any(norm(c) == key for c in hand)
                opening += 1 if in_hand else 0
            d = {"combat": 0, "noncombat": 0}
            for src, v in (p.get("card_damage") or {}).items():
                if norm(src) == key:
                    d["combat"] += v.get("combat", 0)
                    d["noncombat"] += v.get("noncombat", 0)
            k = [x for x in p.get("card_kills", []) if norm(x["card"]) == key]
            if casts:
                cast_games += 1
                n_casts += len(casts)
                first_turns.append(casts[0]["turn"] or None)
                places_cast.append(p["place"])
            else:
                places_not.append(p["place"])
            dmg_c += d["combat"]
            dmg_n += d["noncombat"]
            kills += len(k)
            rows.append({"round": g["round"], "place": p["place"], "in_opening_hand": in_hand,
                         "casts": [{"turn": c["turn"], "own_turn": c.get("own_turn", True)} for c in casts],
                         "damage": d, "kills": [results["decks"].get(x["victim"], {}).get("name", x["victim"])
                                                for x in k]})
        n = len(games)
        tags = sorted(classify(info) - {"creature"}) if info else []
        combos_in = [c for c in (combo_data or {}).get("included", []) if any(norm(x) == key for x in c["pieces"])]
        e = edh_cards.get(name) or (edh_cards.get(info["name"]) if info else None) or {}
        gfs = gf_focus.get(name) or {}
        avg_cast, avg_not = _avg(places_cast), _avg(places_not)

        # ---- plain observations: (+) for, (−) against, (·) neutral
        obs = []
        if cast_games:
            t_txt = f", first cast on your turn {round(_avg(first_turns), 1)} on average" if _avg(first_turns) else ""
            obs.append(("·", f"Cast in {cast_games} of {n} games ({n_casts} cast{'s' if n_casts != 1 else ''} in total){t_txt}."))
        elif n:
            seen = f" Played on purpose, the deck draws it by turn 8 in {gfs['seen_by_t8']}% of games, so it was " \
                   f"probably just not drawn." if gfs.get("seen_by_t8") is not None and gfs["seen_by_t8"] < 60 else ""
            obs.append(("−" if not seen else "·", f"Never cast in {n} games.{seen}"))
        if dmg_c + dmg_n:
            parts = [f"{dmg_n} non-combat" if dmg_n else "", f"{dmg_c} combat" if dmg_c else ""]
            obs.append(("+", f"Dealt {dmg_c + dmg_n} damage to opponents ({', '.join(x for x in parts if x)})."))
        if kills:
            obs.append(("+", f"Finished off {kills} opponent{'s' if kills != 1 else ''}."))
        if avg_cast is not None and avg_not is not None and len(places_cast) >= 2 and len(places_not) >= 2:
            if avg_cast <= avg_not - 0.5:
                obs.append(("+", f"Games where it was cast went better: average place {avg_cast} vs. {avg_not}."))
            elif avg_cast >= avg_not + 0.5:
                obs.append(("−", f"Games where it was cast went worse: average place {avg_cast} vs. {avg_not}."))
        wins = [c for c in combos_in if c["wins"]]
        if wins:
            obs.append(("+", f"Part of {len(wins)} game-winning combo{'s' if len(wins) != 1 else ''}."))
        elif combos_in:
            obs.append(("·", f"Part of {len(combos_in)} combo{'s' if len(combos_in) != 1 else ''} (not game-winning)."))
        if e.get("inclusion") is not None:
            sign = "+" if e["inclusion"] >= 30 else ("−" if e["inclusion"] < 5 else "·")
            obs.append((sign, f"Played in {e['inclusion']:.0f}% of EDHREC decks with your commander."))
        elif edh_cards and not is_cmd:
            obs.append(("·", "Not on EDHREC's list for your commander – an unusual pick."))
        cmc = (info or {}).get("cmc") or 0
        if cmc >= 6 and gfs.get("avg_cast_turn") and gfs["avg_cast_turn"] >= 8 and not is_cmd:
            obs.append(("−", f"Expensive: when the deck plays on purpose, it's cast on turn {gfs['avg_cast_turn']} "
                             f"on average."))

        out.append({
            "card": name, "commander": is_cmd, "cmc": (info or {}).get("cmc"), "type": (info or {}).get("type_line", ""),
            "roles": [ROLE_WORDS.get(r, r) for r in tags], "price": card_db.price(name) if card_db else None,
            "edhrec": e.get("inclusion"), "games": n, "cast_games": cast_games, "casts": n_casts,
            "avg_first_turn": _avg(first_turns), "opening_hand": opening, "opening_known": opening_known,
            "damage": {"combat": dmg_c, "noncombat": dmg_n}, "kills": kills,
            "avg_place_cast": avg_cast, "avg_place_not": avg_not, "goldfish": gfs,
            "combos": [{"pieces": c["pieces"], "produces": c["produces"][:2], "wins": c["wins"], "url": c["url"]}
                       for c in combos_in[:4]],
            "observations": [{"sign": s, "text": t} for s, t in obs], "per_game": rows,
            "small_sample": n < 10,
        })
    return out
