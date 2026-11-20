"""Upgrade suggestions with prices: what to add and cut, best value for a budget.

Each possible addition gets an impact score from what's known about it:
  * EDHREC: how many decks with your commander play it, and its synergy with your commander
  * the opponent decks found for this test
  * whether it fixes one of your weak points (ramp, draw, removal, board wipes, interaction)
  * whether it completes a combo (only combos allowed in your bracket)
Cuts come from cards you never cast in testing and cards rarely played with your commander.
Within the budget, the highest-impact additions that still fit the remaining money are picked.
"""
from .analysis import MIN_GAMES_NEVER_CAST, classify, is_basic

ROLE_FOR_WEAKNESS = {
    "Slow mana development": "ramp", "Light on ramp pieces": "ramp", "Commander arrives late": "ramp",
    "No early plays": "ramp", "Light on card-draw sources": "draw", "Low card flow": "draw",
    "Combo rarely comes together": "draw", "Light on spot removal spells": "removal", "Weak defence": "removal",
    "Dies to commander damage": "removal", "Few board wipes": "wipe", "Can't stop combos/alt-wins": "counter",
}
ROLE_WORDS = {"ramp": "ramp", "draw": "card draw", "removal": "removal", "wipe": "board wipe",
              "counter": "interaction"}


def recommend(deck, profile, card_db, bracket, weak_titles, analysis, combo_data, edh, opponents,
              budget_eur=None, max_swaps=12):
    ident = set(profile["identity"])
    have = {n.lower() for n in deck.all_names()}
    needed = {ROLE_FOR_WEAKNESS[t] for t in weak_titles if t in ROLE_FOR_WEAKNESS}
    gc_room = 0 if (bracket or 3) <= 2 else (3 - len(profile["game_changers"]) if bracket == 3 else 99)

    # ---- candidates to add
    cand = {}

    def add(name, score, why):
        if name.lower() in have or is_basic(name):
            return
        c = cand.setdefault(name, {"card": name, "score": 0.0, "why": []})
        c["score"] += score
        if why and why not in c["why"]:
            c["why"].append(why)

    edh_cards = (edh or {}).get("cards") or {}
    for name, e in edh_cards.items():
        incl = (e.get("inclusion") or 0) / 100
        syn = max(0.0, e.get("synergy") or 0)
        if incl >= 0.15 or syn >= 0.2:
            add(name, 0.6 * incl + 0.5 * syn, f"in {e['inclusion']:.0f}% of EDHREC decks" if e.get("inclusion") else "")
    n_opp = max(1, len(opponents))
    for a in analysis.get("add_candidates", []):
        add(a["card"], 0.2 * min(1.0, a["in_decks"] / n_opp * 3), f"in {a['in_decks']} opponent decks")
    for a in (combo_data or {}).get("almost", []):
        if a.get("wins"):
            add(a["missing"], 0.45, "completes a combo")

    try:
        card_db.resolve(list(cand))
        top = sorted(cand.values(), key=lambda c: -c["score"])[:80]
        card_db.cheapest([c["card"] for c in top], 1.0)
    except Exception:
        pass
    adds = []
    for name, c in cand.items():
        info = card_db.get(name)
        if not info or not set(info["color_identity"]) <= ident or not info.get("legal_commander", True):
            continue
        if info["game_changer"] and gc_room <= 0:
            continue
        tags = classify(info)
        if "land" in tags and info["type_line"].startswith("Basic"):
            continue
        fits = sorted(tags & needed)
        if fits:
            c["score"] += 0.3
            c["why"].insert(0, "adds " + " / ".join(ROLE_WORDS.get(f, f) for f in fits))
        price = card_db.price(name)
        adds.append({"card": info["name"], "score": round(c["score"], 3), "why": ", ".join(c["why"][:2]),
                     "price": price, "tags": sorted(tags), "fits_need": bool(fits),
                     "game_changer": info["game_changer"]})
    adds.sort(key=lambda a: -a["score"])

    # ---- candidates to cut
    perf = {r["card"].lower(): r for r in analysis.get("card_performance", [])}
    games = analysis.get("games_played") or 0
    protected = {n.lower() for c in (combo_data or {}).get("included", []) for n in c["pieces"]}
    role_counts = {k: profile.get(k, 0) for k in ("ramp", "draw", "removal", "wipes")}
    cuts = []
    for q, name in deck.cards:
        info = card_db.get(name)
        if not info or name.lower() in protected:
            continue
        tags = classify(info)
        if "land" in tags:
            continue
        # keep scarce roles
        if ("ramp" in tags and role_counts["ramp"] <= 10) or ("draw" in tags and role_counts["draw"] <= 9) or \
                ("removal" in tags and role_counts["removal"] <= 8) or ("wipe" in tags and role_counts["wipes"] <= 2):
            continue
        score, why = 0.0, []
        r = perf.get(name.lower())
        if r and games >= MIN_GAMES_NEVER_CAST and r["cast_games"] == 0:
            score += 0.4
            why.append("never cast in testing")
        e = edh_cards.get(name) or edh_cards.get(info["name"])
        if edh_cards:
            incl = (e or {}).get("inclusion")
            if incl is None:
                score += 0.25
                why.append("rarely played with your commander")
            elif incl < 10:
                score += 0.25 * (1 - incl / 10)
                why.append(f"in {incl:.0f}% of EDHREC decks")
        if (info.get("cmc") or 0) >= 6:
            score += 0.1
            why.append(f"costs {int(info['cmc'])}")
        if score > 0:
            cuts.append({"card": name, "score": round(score, 3), "why": ", ".join(why)})
    cuts.sort(key=lambda c: -c["score"])

    # ---- pick swaps: the highest-impact additions that still fit the remaining budget
    # (a swap slot is limited by sensible cuts, so impact comes first and price is the constraint)
    order = [a for a in adds if a["price"] is not None]
    swaps, spent = [], 0.0
    for a in order:
        if len(swaps) >= min(max_swaps, len(cuts)):
            break
        if budget_eur and spent + a["price"] > budget_eur:
            continue
        cut = cuts[len(swaps)]
        swaps.append({"add": a["card"], "price": a["price"], "why": a["why"], "fits_need": a["fits_need"],
                      "cut": cut["card"], "cut_why": cut["why"]})
        spent += a["price"]
    swaps.sort(key=lambda s: -next(a["score"] for a in adds if a["card"] == s["add"]))
    return {"budget": budget_eur, "spent": round(spent, 2), "swaps": swaps,
            "top_adds": adds[:15], "cuts": cuts[:10]}


def edhrec_view(deck, card_db, edh):
    """Staples you don't play and your unusual picks."""
    if not edh:
        return None
    cards = edh["cards"]
    have = {n.lower() for n in deck.all_names()}
    try:
        card_db.cheapest([n for n, e in cards.items()
                          if (e.get("inclusion") or 0) >= 30 and n.lower() not in have and not is_basic(n)], 1.0)
    except Exception:
        pass
    missing = [{"card": n, "inclusion": e["inclusion"], "synergy": e.get("synergy"), "price": card_db.price(n)}
               for n, e in cards.items()
               if n.lower() not in have and not is_basic(n) and (e.get("inclusion") or 0) >= 30]
    missing.sort(key=lambda m: -(m["inclusion"] or 0))
    unusual = []
    for q, n in deck.cards:
        info = card_db.get(n)
        if info and "land" in classify(info):
            continue
        e = cards.get(n) or (cards.get(info["name"]) if info else None)
        incl = e.get("inclusion") if e else None
        if incl is None or incl < 5:
            unusual.append({"card": n, "inclusion": incl})
    unusual.sort(key=lambda u: (u["inclusion"] is not None, u["inclusion"] or 0))
    in_deck = [cards[n]["inclusion"] for n in cards if n.lower() in have and cards[n].get("inclusion") is not None]
    return {"url": edh["url"], "decks": edh.get("decks"), "missing": missing[:12], "unusual": unusual[:10],
            "avg_inclusion_of_yours": round(sum(in_deck) / len(in_deck), 1) if in_deck else None}
