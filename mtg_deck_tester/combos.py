"""Combo and consistency analysis for the report.

* finds every combo in your deck (Commander Spellbook; opponents are not looked up)
* goldfishes your deck thousands of times to measure speed and consistency (goldfish.py)
* counts the counterspells and instant-speed removal in the field
* cross-checks the Forge games: did Forge's AI have all combo pieces and still not win?
"""
from .analysis import classify
from .goldfish import Goldfish, chance_holding, norm

MAX_SIM_COMBOS = 12


def _rank(c):
    return (not c["wins"], -(c["popularity"] or 0), len(c["pieces"]))


def _interaction(deck, card_db):
    counters = instant_removal = 0
    for q, n in deck.cards:
        info = card_db.get(n) if card_db else None
        if not info:
            continue
        tags = classify(info)
        fast = "instant" in (info.get("type_line") or "").lower() or "flash" in (info.get("oracle") or "").lower()
        if "counter" in tags:
            counters += q
        elif fast and ("removal" in tags or "wipe" in tags):
            instant_removal += q
    return counters, instant_removal


def _combo_view(c, stats=None):
    return {"pieces": [p["name"] for p in c["pieces"]], "produces": c["produces"][:4], "wins": c["wins"],
            "bracket": c["bracket"], "bracket_label": c["bracket_label"], "url": c["url"],
            "prerequisites": c["prerequisites"][:240], "mana_value_needed": c["mana_value_needed"],
            "speed": stats}


def analyze(user_deck, opponents, card_db, bracket, spellbook, log=print, n_user=6000, focus=()):
    out = {"available": True, "error": "", "included": [], "almost": [], "over_bracket": [],
           "goldfish": None, "interaction": {}, "field": {}}
    sb_ok = spellbook is not None

    def find(deck):
        nonlocal sb_ok
        if not sb_ok:
            return {"included": [], "almost": []}
        try:
            return spellbook.find(deck)
        except Exception as e:
            sb_ok = False
            out["available"] = False
            out["error"] = f"Commander Spellbook could not be reached ({str(e)[:120]})."
            log("Combo database unavailable: " + out["error"])
            return {"included": [], "almost": []}

    # ---- your deck
    log("Looking up combos in your deck (Commander Spellbook)...")
    mine = find(user_deck)
    included = sorted(mine["included"], key=_rank)
    deck_names = {norm(n) for n in user_deck.all_names()}
    sim_combos = [c for c in included if {norm(p["name"]) for p in c["pieces"]} <= deck_names][:MAX_SIM_COMBOS]
    log(f"  {len(included)} combo(s) found, {sum(1 for c in included if c['wins'])} of them game-winning. "
        "Goldfishing your deck...")
    gf = Goldfish(user_deck, card_db, sim_combos, focus=focus).run(
        n_user, seed=1, win_combo_idx=[i for i, c in enumerate(sim_combos) if c["wins"]])
    out["goldfish"] = gf
    sim_map = {id(c): st for c, st in zip(sim_combos, gf["combo_each"])}
    out["included"] = [_combo_view(c, sim_map.get(id(c))) for c in included[:20]]
    out["n_included"] = len(included)
    out["n_wins"] = sum(1 for c in included if c["wins"])
    if bracket:
        out["over_bracket"] = [_combo_view(c) for c in included if c["bracket"] and c["bracket"] > bracket][:8]

    # one card away, legal in your colours and within your bracket
    have = {norm(n) for n in user_deck.all_names()}
    almost = []
    for c in sorted(mine["almost"], key=_rank):
        missing = [p["name"] for p in c["pieces"] if norm(p["name"]) not in have]
        if len(missing) != 1 or (bracket and c["bracket"] and c["bracket"] > bracket):
            continue
        v = _combo_view(c)
        v["missing"] = missing[0]
        almost.append(v)
    seen_missing, out["almost"] = set(), []
    for a in almost:
        if a["missing"] not in seen_missing:
            seen_missing.add(a["missing"])
            out["almost"].append(a)
        if len(out["almost"]) >= 8:
            break

    # ---- interaction: yours and the field's
    uc, ur = _interaction(user_deck, card_db)
    out["interaction"] = {"counters": uc, "instant_removal": ur}

    # ---- the field: counterspells and instant-speed removal (from card data, no combo lookups)
    p_counter, opp_inter = [], []
    for od in opponents:
        oc, orr = _interaction(od, card_db)
        opp_inter.append((oc, orr))
        p_counter.append(chance_holding(oc))
    n = max(1, len(opponents))
    avg_p = sum(p_counter) / n if p_counter else 0
    out["field"] = {
        "opponents": len(opponents),
        "avg_counters": round(sum(c for c, _ in opp_inter) / n, 1),
        "avg_instant_removal": round(sum(r for _, r in opp_inter) / n, 1),
        # chance that at least one of three random opponents has drawn a counterspell by turn 6
        "pod_counter_by_t6": round(100 * (1 - (1 - avg_p) ** 3), 1),
    }
    return out


def forge_crosscheck(combo_data, results, user_deck, card_db):
    """How often Forge's AI cast every piece of one of your game-winning combos, and what happened."""
    if not combo_data or not combo_data.get("included"):
        return None
    cmd_names = {norm(c) for c in user_deck.commanders}
    games = [g for g in results["games"] if "D01" in g["players"]]
    assembled, won = 0, 0
    for g in games:
        p = g["players"]["D01"]
        cast = {norm(c) for c in p.get("cards_cast", [])}
        if p.get("commander_turn"):
            cast |= cmd_names
        for c in combo_data["included"]:
            if c["wins"] and all(norm(x) in cast for x in c["pieces"]):
                assembled += 1
                won += 1 if p["place"] == 1 else 0
                break
    return {"games": len(games), "assembled": assembled, "won": won}


def explain_commander_timing(ana, cd):
    """Forge's AI often holds its commander back. If the goldfish shows the deck can cast it on time,
    say so instead of telling the player to change the deck."""
    gf = (cd or {}).get("goldfish") or {}
    m = (ana.get("metrics") or {}).get("commander_turn") or {}
    if not gf or m.get("you") is None:
        return
    for w in ana["weak_points"]:
        if w["title"] != "Commander arrives late":
            continue
        if gf.get("cmd_on_curve", 0) >= 50:
            w["title"] = "Commander arrives late in Forge"
            w["detail"] = (f"In the Forge games your commander came down on turn {m['you']} on average "
                           f"(other decks: {m.get('field')}). Played on purpose, your deck casts it on curve in "
                           f"{gf['cmd_on_curve']}% of games (average turn {gf.get('cmd_avg_turn', '?')}), so this is "
                           "mostly Forge's AI choosing other spells first, not a problem with the deck.")
            ana["suggestions"] = [s for s in ana["suggestions"] if not s.startswith("Prioritise ramp on turns 1–3")]
        else:
            w["detail"] += (f" Even played on purpose, it's cast on curve in only {gf.get('cmd_on_curve')}% of "
                            f"goldfish games, so more early ramp would help.")


def weak_points(cd, bracket):
    """Extra weak points and suggestions from the combo / goldfish analysis."""
    weak, sugg = [], []
    if not cd or not cd.get("goldfish"):
        return weak, sugg
    gf = cd["goldfish"]
    if cd.get("n_wins") and gf.get("combo_any") and gf["combo_any"]["t8"] < 25:
        weak.append(("Combo rarely comes together",
                     f"Goldfishing, your deck assembles a combo by turn 8 in only {gf['combo_any']['t8']}% of games."))
        sugg.append("Add tutors or card draw, or redundant pieces, so your combo shows up more often.")
    win = gf.get("win") or {}
    wa = gf.get("win_any") or {}
    if wa and wa.get("t12", 100) < 50:
        weak.append(("Slow to win on its own",
                     f"Playing alone, your deck wins by turn 12 in only {wa.get('t12')}% of goldfish games "
                     f"(typical: {('turn ' + str(wa['median'])) if wa.get('median') else 'after turn 15'})."))
        sugg.append("Add finishers that end the game quickly: evasive threats, mass pump, drain effects or a combo.")
    if gf["keep7"] < 70:
        weak.append(("Inconsistent opening hands", f"Only {gf['keep7']}% of 7-card hands are keepable (2–5 lands with plays)."))
    if gf["screw"] > 25:
        weak.append(("Mana screw risk", f"{gf['screw']}% of goldfish games miss a land drop by turn 3."))
    if gf["flood"] > 25:
        weak.append(("Flood risk", f"In {gf['flood']}% of games, 8 or more of the first 13 cards are lands."))
    fx = cd.get("forge_check")
    if fx and fx["assembled"] and fx["won"] < fx["assembled"]:
        weak.append(("Forge didn't finish the combo",
                     f"Forge's AI cast every piece of a winning combo in {fx['assembled']} game(s) but won only "
                     f"{fx['won']}. Forge plays combos poorly, so your real win rate is probably higher."))
    field = cd.get("field") or {}
    if cd.get("n_wins") and field.get("pod_counter_by_t6", 0) >= 50:
        sugg.append(f"In a typical pod there's a {field['pod_counter_by_t6']}% chance an opponent holds a counterspell by "
                    "turn 6: protect your combo (your own counters, 'can't be countered' effects) or bait answers first.")
    if cd.get("over_bracket"):
        weak.append(("Combo above your bracket",
                     f"{len(cd['over_bracket'])} combo(s) in your deck are rated above bracket {bracket} by Commander "
                     "Spellbook (see the combo section)."))
    if cd.get("almost") and not cd.get("n_wins"):
        a = cd["almost"][0]
        sugg.append(f"Adding {a['missing']} would give you a combo: {' + '.join(a['pieces'])}.")
    return weak, sugg
