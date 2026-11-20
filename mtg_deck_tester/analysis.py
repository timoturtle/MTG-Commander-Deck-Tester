"""Turn tournament results into weak points and improvement suggestions."""
import json
import re
from collections import Counter, defaultdict

from .net import post_json

USER = "D01"

# Typical ranges for a functional Commander deck (community rules of thumb)
NORMS = {"lands": (34, 39), "ramp": (9, 15), "draw": (9, 15), "removal": (7, 14), "wipes": (2, 4)}


def classify(info):
    """Rough role tags from type line and oracle text."""
    t = (info.get("type_line") or "").lower()
    o = (info.get("oracle") or "").lower()
    tags = set()
    if "land" in t and "//" not in t:
        tags.add("land")
        return tags
    if "creature" in t:
        tags.add("creature")
    if re.search(r"add \{|add (one|two|three) mana|mana of any", o) or \
            re.search(r"search your library for (a|up to \w+) .*land", o) or "treasure token" in o:
        tags.add("ramp")
    if re.search(r"draws? (a|two|three|\w+) cards?|draw cards equal|investigate|"
                 r"exile the top .* you may (play|cast)", o):
        tags.add("draw")
    if re.search(r"(destroy|exile) (all|each) (creature|nonland|artifact|enchantment|permanent)|"
                 r"all creatures get -|deals \d+ damage to each creature|return all .* to (their|its) owner", o):
        tags.add("wipe")
    elif re.search(r"(destroy|exile) target|counter target|return target .* to its owner|"
                   r"deals \d+ damage to (any )?target|fights? (target|another)|target .* sacrifices", o):
        tags.add("removal")
    if re.search(r"counter target", o):
        tags.add("counter")
    if re.search(r"protection from|hexproof|indestructible|phase out", o):
        tags.add("protection")
    if re.search(r"search your library for a card|search your library for an? (creature|instant|sorcery|artifact|enchantment)", o):
        tags.add("tutor")
    return tags


def deck_profile(deck, card_db):
    counts, cmc_total, nonland, unknown, unknown_qty = Counter(), 0.0, 0, [], 0
    identity, game_changers = set(), []
    for c in deck.commanders:
        info = card_db.get(c)
        if info:
            identity |= set(info["color_identity"])
            if info["game_changer"]:
                game_changers.append(info["name"])
    for q, n in deck.cards:
        info = card_db.get(n)
        if not info:
            unknown.append(n)
            unknown_qty += q
            continue
        tags = classify(info)
        for tg in tags:
            counts[tg] += q
        if "land" not in tags:
            cmc_total += info["cmc"] * q
            nonland += q
        if info["game_changer"]:
            game_changers.append(info["name"])
    return {"lands": counts["land"], "ramp": counts["ramp"], "draw": counts["draw"],
            "removal": counts["removal"], "wipes": counts["wipe"], "creatures": counts["creature"],
            "counters": counts["counter"], "protection": counts["protection"], "tutors": counts["tutor"],
            "avg_cmc": round(cmc_total / nonland, 2) if nonland else 0,
            "identity": sorted(identity), "game_changers": game_changers, "unknown": unknown,
            "unknown_count": unknown_qty}


def estimate_bracket(profile):
    gc = len(profile["game_changers"])
    if gc >= 4:
        return 4, f"{gc} Game Changers means bracket 4 or higher."
    if gc >= 1:
        return 3, f"{gc} Game Changer(s) means at least bracket 3."
    return 2, "No Game Changers: bracket 1–2 (bracket 3 if you run fast combos or mass land denial is off-limits)."


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


def game_metrics(results):
    """Per-player-game metrics for the user vs. the rest of the field."""
    mine, field = defaultdict(list), defaultdict(list)
    for g in results["games"]:
        for d, p in g["players"].items():
            bucket = mine if d == USER else field
            bucket["place"].append(p["place"])
            bucket["lands_t4"].append(sum(v for k, v in p["lands_by_turn"].items() if int(k) <= 4)
                                      if p["own_turns"] >= 4 else None)
            bucket["first_spell"].append(p["first_spell_turn"])
            bucket["commander_turn"].append(p["commander_turn"])
            bucket["damage_dealt"].append(p["damage_dealt"])
            bucket["damage_taken"].append(p["damage_taken"])
            if "damage_dealt_combat" in p:
                bucket["damage_dealt_combat"].append(p["damage_dealt_combat"])
                bucket["damage_dealt_noncombat"].append(p["damage_dealt_noncombat"])
                bucket["damage_taken_combat"].append(p["damage_taken_combat"])
                bucket["damage_taken_noncombat"].append(p["damage_taken_noncombat"])
            bucket["mulligans"].append(p["mulligans"])
            bucket["spells_per_turn"].append(round(p["spells_cast"] / p["own_turns"], 2) if p["own_turns"] else None)
            bucket["elim_turn"].append(p["elim_round"])
            bucket["survived"].append(0 if p["eliminated"] else 1)
    keys = ["place", "lands_t4", "first_spell", "commander_turn", "damage_dealt", "damage_dealt_combat",
            "damage_dealt_noncombat", "damage_taken", "damage_taken_combat", "damage_taken_noncombat",
            "mulligans", "spells_per_turn", "elim_turn", "survived"]
    return {k: {"you": _avg(mine[k]), "field": _avg(field[k])} for k in keys}


def card_performance(results, deck, card_db):
    games = [g for g in results["games"] if USER in g["players"]]
    cast_in, places_when_cast = Counter(), defaultdict(list)
    for g in games:
        p = g["players"][USER]
        for c in set(p["cards_cast"]):
            cast_in[c] += 1
            places_when_cast[c].append(p["place"])
    rows = []
    for q, n in deck.cards:
        info = card_db.get(n) or {}
        fname = info.get("forge_name", n)
        tags = classify(info) if info else set()
        if "land" in tags:
            continue
        k = cast_in.get(fname, 0) + (cast_in.get(n, 0) if n != fname else 0)
        pl = places_when_cast.get(fname, []) + (places_when_cast.get(n, []) if n != fname else [])
        rows.append({"card": n, "cmc": info.get("cmc"), "tags": sorted(tags), "cast_games": k,
                     "avg_place_when_cast": _avg(pl)})
    rows.sort(key=lambda r: (r["cast_games"], -(r["cmc"] or 0)))
    return rows, len(games)


BASIC_LANDS = {"plains", "island", "swamp", "mountain", "forest", "wastes"}
MIN_GAMES_NEVER_CAST = 10  # below this, "never cast" mostly means "never drawn"


def is_basic(name):
    return name.lower().replace("snow-covered ", "").strip() in BASIC_LANDS


def _is_land(name, card_db):
    info = card_db.get(name) if card_db else None
    if info:
        return "land" in classify(info)
    base = name.lower().replace("snow-covered ", "")
    return base in BASIC_LANDS


def hand_text(cards, card_db):
    """'Sol Ring, Shock, 2× Command Tower + 3 lands' style summary (spells first)."""
    from collections import Counter as C
    spells = C(c for c in cards if not _is_land(c, card_db))
    lands = C(c for c in cards if _is_land(c, card_db))
    fmt = lambda cnt: [f"{n}× {c}" if n > 1 else c for c, n in cnt.items()]
    parts = fmt(spells) + fmt(lands)
    return ", ".join(parts)


def early_game(results, card_db):
    """Opening hands kept and turn-1/turn-2 plays of the tested deck, per game."""
    rows = []
    for g in sorted([g for g in results["games"] if USER in g["players"]], key=lambda g: g["round"]):
        p = g["players"][USER]
        cbt = {int(k): v for k, v in (p.get("casts_by_turn") or {}).items()}
        hand = p.get("opening_hand")
        n_lands = sum(1 for c in hand if _is_land(c, card_db)) if hand is not None else None

        def turn(t):
            if p["own_turns"] < t:
                return None  # never got that turn
            return cbt.get(t, [])
        rows.append({"round": g["round"], "place": p["place"], "hand": hand,
                     "hand_text": hand_text(hand, card_db) if hand else None,
                     "lands_in_hand": n_lands, "kept": p.get("kept_size") or (len(hand) if hand else None),
                     "mulligans": p.get("mulligans", 0), "t1": turn(1), "t2": turn(2)})
    reached1 = [r for r in rows if r["t1"] is not None]
    reached2 = [r for r in rows if r["t2"] is not None]
    both = [r for r in rows if r["t1"] and r["t2"]]
    hands = [r for r in rows if r["hand"] is not None]
    return {
        "games": rows,
        "t1_play": sum(1 for r in reached1 if r["t1"]), "t1_games": len(reached1),
        "t2_play": sum(1 for r in reached2 if r["t2"]), "t2_games": len(reached2),
        "both": len(both), "n": len(rows),
        "hands_recorded": len(hands),
        "avg_kept": _avg([r["kept"] for r in rows]),
        "avg_lands_in_hand": _avg([r["lands_in_hand"] for r in hands]),
    }


def weak_points_and_suggestions(results, deck, profile, card_db, opponents, bracket):
    m = game_metrics(results)
    weak, strengths, sugg = [], [], []
    you, fld = (lambda k: m[k]["you"]), (lambda k: m[k]["field"])

    def worse(k, margin, higher_is_bad=True):
        a, b = you(k), fld(k)
        if a is None or b is None:
            return False
        return (a - b > margin) if higher_is_bad else (b - a > margin)

    # ---- game-derived weak points
    if worse("lands_t4", 0.5, higher_is_bad=False):
        weak.append(("Slow mana development",
                     f"You hit {you('lands_t4')} lands by your 4th turn vs. {fld('lands_t4')} for the field."))
    if worse("commander_turn", 1.0):
        weak.append(("Commander arrives late",
                     f"Your commander was cast on turn {you('commander_turn')} on average vs. {fld('commander_turn')} for other decks."))
    if worse("first_spell", 0.8):
        weak.append(("Slow first plays", f"First spell on turn {you('first_spell')} vs. {fld('first_spell')}."))
    if worse("damage_dealt", (fld('damage_dealt') or 0) * 0.25, higher_is_bad=False):
        weak.append(("Low pressure", f"You dealt {you('damage_dealt')} damage per game vs. {fld('damage_dealt')} for the field - "
                                      "the deck struggles to close games. (Life loss that isn't damage, "
                                      "like drain effects, isn't counted here.)"))
    elif you("damage_dealt") and fld("damage_dealt") and you("damage_dealt") > fld("damage_dealt") * 1.25:
        split = (f" ({you('damage_dealt_combat')} combat, {you('damage_dealt_noncombat')} non-combat)"
                 if you("damage_dealt_combat") is not None else "")
        strengths.append(f"Strong pressure: {you('damage_dealt')} damage per game{split} vs. {fld('damage_dealt')}.")
    if worse("damage_taken", (fld('damage_taken') or 0) * 0.25):
        weak.append(("Weak defence", f"You took {you('damage_taken')} damage per game vs. {fld('damage_taken')} - "
                                      "opponents find you an easy target."))
    if worse("mulligans", 0.3):
        weak.append(("Frequent mulligans", f"{you('mulligans')} mulligans per game vs. {fld('mulligans')}."))
    if worse("spells_per_turn", 0.3, higher_is_bad=False):
        weak.append(("Low card flow", f"{you('spells_per_turn')} spells per turn vs. {fld('spells_per_turn')} - "
                                       "you run out of things to do."))
    if you("place") is not None and fld("place") is not None and you("place") < fld("place") - 0.4:
        strengths.append(f"Average pod finish {you('place')} vs. {fld('place')} for the field.")

    games = [g for g in results["games"] if USER in g["players"]]
    reasons = Counter(g["players"][USER]["loss_reason"] for g in games if g["players"][USER]["eliminated"])
    killers = Counter(g["killers"].get(USER) for g in games if g["killers"].get(USER))
    draws = sum(1 for g in games if g["draw"])
    cmd_deaths = sum(v for r, v in reasons.items() if "21 damage" in r)
    alt_deaths = sum(v for r, v in reasons.items() if "spell" in r or "effect" in r)
    if cmd_deaths >= 2:
        weak.append(("Dies to commander damage", f"{cmd_deaths} losses to 21 commander damage - you need blockers, "
                                                  "spot removal or protection against big commanders."))
    if alt_deaths >= 2:
        weak.append(("Can't stop combos/alt-wins", f"{alt_deaths} losses to spells or effects - add instant-speed interaction."))
    if games and draws / len(games) >= 0.34:
        weak.append(("Games stall out", f"{draws} of {len(games)} games hit the time limit - the deck lacks finishers."))

    # ---- composition weak points (only if the card data could be looked up)
    known_ok = profile.get("unknown_count", len(profile["unknown"])) <= 0.2 * max(1, sum(q for q, _ in deck.cards))
    lo, hi = NORMS["lands"]
    if not known_ok:
        pass
    elif profile["lands"] < lo:
        weak.append(("Few lands", f"{profile['lands']} lands; most Commander decks run {lo}–{hi}."))
    elif profile["lands"] > hi:
        weak.append(("Many lands", f"{profile['lands']} lands; you may flood. Typical is {lo}–{hi}."))
    for k, label in (("ramp", "ramp pieces"), ("draw", "card-draw sources"), ("removal", "spot removal spells")):
        if known_ok and profile[k] < NORMS[k][0]:
            weak.append((f"Light on {label}", f"About {profile[k]} {label}; aim for {NORMS[k][0]}+ (detected from card text)."))
    if known_ok and bracket and bracket >= 2 and profile["wipes"] < NORMS["wipes"][0]:
        weak.append(("Few board wipes", f"{profile['wipes']} board wipes; 2–4 helps you recover when behind."))
    if known_ok and profile["avg_cmc"] > 3.6:
        weak.append(("Top-heavy curve", f"Average mana value {profile['avg_cmc']} (non-land); above ~3.5 slows you down."))

    # ---- cut candidates: rarely cast, expensive
    perf, n_games = card_performance(results, deck, card_db)
    # never cast in testing: always listed; with few games the report shows how likely it is that the
    # card simply wasn't drawn (goldfish), and cut suggestions only use it from MIN_GAMES_NEVER_CAST games
    cuts = [dict(r) for r in perf if r["cast_games"] == 0] if n_games else []

    # ---- add candidates: popular in the similar decks, legal in your colours
    ident = set(profile["identity"])
    my_names = {n.lower() for n in deck.all_names()}
    pop = Counter()
    for od in opponents:
        for _, n in od.cards:
            pop[n] += 1
    gc_ok = (bracket or 3) >= 3 and len(profile["game_changers"]) < (3 if (bracket or 3) == 3 else 99)
    needs = {w[0] for w in weak}
    want_tags = set()
    if any("mana" in n.lower() or "ramp" in n.lower() or "lands" in n.lower() for n in needs):
        want_tags.add("ramp")
    if any(k in " ".join(needs).lower() for k in ("card", "flow", "draw")):
        want_tags.add("draw")
    if any(k in " ".join(needs).lower() for k in ("removal", "defence", "commander damage", "combo")):
        want_tags |= {"removal", "counter"}
    if "Few board wipes" in needs:
        want_tags.add("wipe")
    adds = []
    for n, k in pop.most_common(400):
        if n.lower() in my_names or k < 2:
            continue
        info = card_db.get(n)
        if not info or not set(info["color_identity"]) <= ident or not info.get("legal_commander", True):
            continue
        if info["game_changer"] and not gc_ok:
            continue
        tags = classify(info)
        if info["type_line"].startswith("Basic") or is_basic(info["name"]):
            continue
        adds.append({"card": info["name"], "in_decks": k, "tags": sorted(tags),
                     "fits_need": bool(tags & want_tags)})
    adds.sort(key=lambda a: (not a["fits_need"], -a["in_decks"]))
    adds = adds[:12]

    for title, why in weak:
        if title == "Slow mana development" or title == "Light on ramp pieces":
            sugg.append("Add 2–3 cheap ramp pieces (2-mana rocks or land ramp) and cut your most expensive spells.")
        elif title == "Commander arrives late":
            sugg.append("Prioritise ramp on turns 1–3 and cut cards that compete with casting your commander early.")
        elif title in ("Low pressure", "Games stall out"):
            sugg.append("Add 1–2 reliable finishers (mass pump, evasion, or a combo) so games end on your terms.")
        elif title == "Weak defence":
            sugg.append("Add blockers, fog effects or deterrents, and keep removal for the biggest threat at the table.")
        elif title in ("Can't stop combos/alt-wins",):
            sugg.append("Run 2–3 instant-speed answers (counterspells or instant removal) and hold them up late.")
        elif title == "Dies to commander damage":
            sugg.append("Add cheap instant-speed removal for commanders and a few chump-blockers or token makers.")
        elif title == "Light on card-draw sources" or title == "Low card flow":
            sugg.append("Add repeatable card draw (engines that draw every turn) rather than one-shot draw spells.")
        elif title == "Few board wipes":
            sugg.append("Include 1–2 board wipes that fit your plan (one-sided if possible).")
        elif title == "Top-heavy curve":
            sugg.append("Swap 3–4 cards at 6+ mana for 2–3 mana spells that do a similar job.")
        elif title == "Frequent mulligans":
            sugg.append("Check your land count and cheap plays - hands without early lands get sent back.")
    sugg = list(dict.fromkeys(sugg))

    early = early_game(results, card_db)
    if early["t2_games"] >= 3 and early["t2_play"] / early["t2_games"] < 0.5:
        weak.append(("No early plays", f"Only {early['t2_play']} of {early['t2_games']} games had a non-land play "
                                       "on your turn 2. More 1–2 mana ramp or interaction helps."))
        sugg.append("Add more 1–2 mana plays (mana rocks, mana dorks, cheap interaction) so turns 1–2 aren't wasted.")
    if early["hands_recorded"] >= 3 and early["avg_lands_in_hand"] is not None and \
            (early["avg_lands_in_hand"] < 2.5 or early["avg_lands_in_hand"] > 4.5):
        what = "few" if early["avg_lands_in_hand"] < 2.5 else "many"
        weak.append(("Unbalanced opening hands", f"Kept hands had {early['avg_lands_in_hand']} lands on average "
                                                 f"({what}); 3–4 is ideal."))

    killer_names = [(results["decks"][k]["name"], v) for k, v in killers.most_common(3) if k in results["decks"]]
    return {"metrics": m, "weak_points": [{"title": t, "detail": d} for t, d in weak],
            "strengths": strengths, "suggestions": sugg, "cut_candidates": cuts, "add_candidates": adds,
            "loss_reasons": dict(reasons), "eliminated_by": killer_names, "card_performance": perf,
            "draws": draws, "games_played": len(games), "early_game": early,
            "min_games_never_cast": MIN_GAMES_NEVER_CAST}


AI_SYSTEM = ("You are an expert Magic: The Gathering Commander deckbuilder and coach. You get a decklist "
             "and results from AI-vs-AI test games run in Forge (pods of four). Forge's AI plays imperfectly, "
             "so weigh structural problems over single-game noise. Respect the deck's colour identity and the "
             "target Commander bracket (Game Changer limits: bracket 1-2 none, bracket 3 up to three). "
             "If combo data is included, judge combo decks by the goldfish speed and combo data rather than "
             "by Forge results alone, and suggest how to protect or speed up the combos, or how to get them past the field's interaction. "
             "If a budget in EUR is given, keep the total price of your suggested additions within it, using the prices provided. "
             "If focus_cards are given, the player is unsure about these cards: add a section 'Focus cards' with a short "
             "keep / cut / test more recommendation for each, based on the evidence and the card's role in the deck, "
             "and say when the sample is too small to judge. "
             "Answer in Markdown with these sections: 'Summary' (2-3 sentences), 'Weak points' (most important "
             "first, each tied to evidence), 'Swaps' (a table of 6-10 concrete cut -> add pairs with a short reason; "
             "only cut cards that are in the deck; only add real cards legal in the colour identity), and "
             "'How to pilot it' (2-4 tips). Be concise and specific.")


def ai_analysis(api_key, model, deck, profile, analysis, results, bracket, combo_data=None, upgrades=None,
                edhrec_view=None, budget=None, focus_report=None):
    me = next(s for s in results["standings"] if s["id"] == USER)
    payload = {
        "commander": deck.commanders, "bracket": bracket, "colour_identity": profile["identity"],
        "decklist": [f"{q} {n}" for q, n in deck.cards],
        "composition": {k: profile[k] for k in ("lands", "ramp", "draw", "removal", "wipes", "creatures",
                                                 "counters", "protection", "tutors", "avg_cmc")},
        "game_changers": profile["game_changers"],
        "tournament": {"final_rank": me["rank"], "field_size": len(results["standings"]),
                       "pod_places": me["places"], "points": me["points"]},
        "you_vs_field": analysis["metrics"], "loss_reasons": analysis["loss_reasons"],
        "eliminated_most_by": analysis["eliminated_by"],
        "opponents": [{"name": d["name"], "commanders": d["commanders"]} for k, d in results["decks"].items() if k != USER],
        "never_cast": [r["card"] for r in analysis["card_performance"] if r["cast_games"] == 0][:25],
        "most_cast": [(r["card"], r["cast_games"], r["avg_place_when_cast"]) for r in analysis["card_performance"][::-1][:15]],
        "rule_based_weak_points": analysis["weak_points"],
        "opening_hands_and_early_plays": [{k: r[k] for k in ("round", "place", "hand", "mulligans", "t1", "t2")}
                                          for r in analysis["early_game"]["games"]],
        "popular_in_similar_decks_not_in_yours": [a["card"] for a in analysis["add_candidates"]],
    }
    if focus_report:
        payload["focus_cards"] = [{k: f[k] for k in ("card", "cmc", "roles", "price", "edhrec", "games", "cast_games",
                                                     "casts", "avg_first_turn", "damage", "kills", "avg_place_cast",
                                                     "avg_place_not", "goldfish", "combos", "observations")}
                                  for f in focus_report]
    if upgrades:
        payload["budget_eur"] = budget
        payload["priced_upgrade_candidates"] = [{k: a[k] for k in ("card", "price", "why")} for a in upgrades["top_adds"]]
    if edhrec_view:
        payload["edhrec"] = {"popular_cards_missing": edhrec_view["missing"], "unusual_picks": edhrec_view["unusual"]}
    if combo_data:
        payload["combos"] = {
            "note": "Forge's AI plays combos poorly; the goldfish numbers are solo simulations of deliberate play.",
            "your_combos": [{k: c[k] for k in ("pieces", "produces", "wins", "bracket_label", "speed")}
                            for c in combo_data.get("included", [])[:10]],
            "one_card_away": [{"add": a["missing"], "pieces": a["pieces"], "produces": a["produces"]}
                              for a in combo_data.get("almost", [])[:6]],
            "goldfish": combo_data.get("goldfish"),
            "forge_check": combo_data.get("forge_check"),
            "field": combo_data.get("field"),
            "your_interaction": combo_data.get("interaction"),
        }
    res = post_json("https://api.anthropic.com/v1/messages", {
        "model": model, "max_tokens": 2500, "system": AI_SYSTEM,
        "messages": [{"role": "user", "content": "Analyse this test run:\n```json\n" + json.dumps(payload, indent=1) + "\n```"}],
    }, headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"}, timeout=180)
    return "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text")
