"""Demo engine: fakes Forge games in Forge's exact log format so the app can be
tried (and tested) without Java/Forge. Enabled with MTG_DEMO=1."""
import random

from .decklist import Deck

DEMO_OPPONENTS = [
    ("Elf Stampede", ["Lathril, Blade of the Elves"], "BG"),
    ("Dragon's Hoard", ["The Ur-Dragon"], "WUBRG"),
    ("Spellslinger", ["Kess, Dissident Mage"], "UBR"),
    ("Aristocrats", ["Teysa Karlov"], "WB"),
    ("Voltron Knights", ["Sigarda, Host of Herons"], "WG"),
    ("Artifact Engine", ["Urza, Lord High Artificer"], "U"),
    ("Landfall", ["Tatyova, Benthic Druid"], "UG"),
    ("Zombie Horde", ["Wilhelt, the Rotcleaver"], "UB"),
    ("Goblin Rush", ["Krenko, Mob Boss"], "R"),
    ("Enchantress", ["Sythis, Harvest's Hand"], "WG"),
    ("Pirate Treasure", ["Admiral Beckett Brass"], "UBR"),
    ("Superfriends", ["Atraxa, Praetors' Voice"], "WUBG"),
    ("Dinosaurs", ["Gishath, Sun's Avatar"], "WRG"),
    ("Vampire Tribal", ["Edgar Markov"], "WBR"),
    ("Group Hug", ["Kynaios and Tiro of Meletis"], "WURG"),
]
FILLER = ["Sol Ring", "Arcane Signet", "Cultivate", "Swords to Plowshares", "Beast Within",
          "Llanowar Elves", "Rhystic Study", "Counterspell", "Wrath of God", "Grave Titan",
          "Craterhoof Behemoth", "Lightning Bolt", "Kodama's Reach", "Command Tower"]


def demo_opponents(n):
    out = []
    for name, cmd, ident in random.sample(DEMO_OPPONENTS, min(n, len(DEMO_OPPONENTS))):
        cards = [(1, c) for c in random.sample(FILLER, 10)] + [(89, "Forest")]
        d = Deck(name=name, commanders=cmd, cards=cards, url="https://archidekt.com/", bracket=3,
                 source="Demo", views=random.randint(2000, 90000))
        d.identity_hint = set(ident)
        out.append(d)
    return out


def fake_game(deck_ids, decks_by_id, strength):
    """strength: deck id -> float. Produces Forge-style log output."""
    names = {d: f"Ai({i+1})-{d}" for i, d in enumerate(deck_ids)}
    life = {d: 40 for d in deck_ids}
    alive = list(deck_ids)
    lines, turn = [], 0
    hands = []
    for d in deck_ids:
        kept = 7
        if random.random() < 0.25:
            lines.append(f"Mulligan: {names[d]} has mulliganed down to 7 cards.")
            if random.random() < 0.4:
                lines.append(f"Mulligan: {names[d]} has mulliganed down to 6 cards.")
                kept = 6
        lines.append(f"Mulligan: {names[d]} has kept a hand of {kept} cards")
        pool = [n for _, n in decks_by_id[d].cards]
        weights = [q for q, _ in decks_by_id[d].cards]
        hand = random.choices(pool, weights=weights, k=kept)
        hands.append(f"Opening Hand: {names[d]}: " + "; ".join(hand))
    own = {d: 0 for d in deck_ids}
    while len(alive) > 1 and turn < 60:
        for d in list(alive):
            if d not in alive or len(alive) == 1:
                continue
            turn += 1
            own[d] += 1
            lines.append(f"Turn: Turn {turn} ({names[d]})")
            deck = decks_by_id[d]
            if own[d] <= 7 and random.random() < 0.75 + 0.1 * strength[d]:
                lines.append(f"Land: {names[d]} played Forest")
            pool = [n for _, n in deck.cards if n != "Forest"] or ["Forest"]
            for _ in range(random.randint(0, 2)):
                if random.random() < 0.3 + 0.1 * own[d]:
                    lines.append(f"Add To Stack: {names[d]} cast {random.choice(pool)}")
            if own[d] == random.randint(2, 6):
                lines.append(f"Add To Stack: {names[d]} cast {deck.commanders[0]}")
            if own[d] >= 3:
                tgt = random.choice([x for x in alive if x != d])
                dmg = max(1, int(random.gauss(4 + 3 * strength[d], 3)))
                src = deck.commanders[0] if random.random() < 0.5 else random.choice(pool)
                lines.append(f"Damage: {src} deals {dmg} combat damage to {names[tgt]}.")
                lines.append(f"Life: Life: {names[tgt]} {life[tgt]} > {life[tgt]-dmg}")
                life[tgt] -= dmg
                if life[tgt] <= 0:
                    alive.remove(tgt)
    lines.append("Game Outcome: Turn %d" % (turn // 2))
    for d in deck_ids:
        if d in alive and len(alive) == 1:
            lines.append(f"Game Outcome: {names[d]} has won because all opponents have lost")
        elif d in alive:
            lines.append(f"Game Outcome: {names[d]} has accepted that the game is a draw")
        else:
            lines.append(f"Game Outcome: {names[d]} has lost because life total reached 0")
    # Forge prints newest-first then reverses; emulate the final chronological print
    out = "Simulation mode\n" + "\n".join(hands) + "\n" + "\n".join(lines)
    if len(alive) == 1:
        out += f"\n\nGame Result: Game 1 ended in {random.randint(20000, 90000)} ms. {names[alive[0]]} has won!\n"
    else:
        out += "\nStopping slow match as draw\n\nGame Result: Game 1 ended in a Draw! Took 600000 ms.\n"
    return out


class DemoSpellbook:
    """Pretend combo database for demo mode: invents combos out of each deck's own cards."""

    def find(self, deck):
        rnd = random.Random(deck.name)
        names = [n for _, n in deck.cards if n not in ("Forest", "Mountain", "Island", "Swamp", "Plains")]
        if len(names) < 3 or rnd.random() < 0.4:
            return {"included": [], "almost": []}

        def combo(pieces, wins=True):
            return {"id": "0", "url": "https://commanderspellbook.com/", "pieces": [{"name": p, "zones": ["B"]} for p in pieces],
                    "commander_pieces": [], "templates": [], "produces": ["Infinite damage"] if wins else ["Infinite tokens"],
                    "wins": wins, "mana_value_needed": 0, "mana_needed": "", "prerequisites": "",
                    "bracket_tag": "P", "bracket_label": "Powerful", "bracket": 3, "popularity": rnd.randint(10, 5000),
                    "identity": ""}
        a, b, c = rnd.sample(names, 3)
        return {"included": [combo([a, b]), combo([b, c], wins=False)],
                "almost": [combo([a, "Demo Missing Piece"])]}


def demo_card_data(card_db, decks):
    """Invent card data (types, costs, prices) for demo decks so every report section has content."""
    card_db.resolve = lambda names: []
    card_db.cheapest = lambda *a, **k: None
    card_db.save = lambda: None
    names = {n for d in decks for n in d.all_names()} | {f"Demo Staple {i}" for i in range(1, 16)}
    for n in names:
        rnd = random.Random(n)
        base = n.lower()
        if base in ("forest", "mountain", "island", "swamp", "plains"):
            info = {"type_line": f"Basic Land — {n}", "cmc": 0, "oracle": "", "power": None, "eur": 0.1}
        else:
            kind = rnd.choice(["creature"] * 5 + ["ramp", "draw", "removal", "wipe"])
            cmc = rnd.randint(1, 6)
            info = {"type_line": "Creature — Goblin" if kind == "creature" else "Sorcery", "cmc": cmc,
                    "power": str(rnd.randint(1, 5)) if kind == "creature" else None,
                    "oracle": {"creature": "", "ramp": "Search your library for a basic land card, put it onto the battlefield tapped.",
                               "draw": "Draw two cards.", "removal": "Destroy target creature.",
                               "wipe": "Destroy all creatures."}[kind],
                    "eur": round(rnd.choice([0.2, 0.5, 1, 2, 4, 8, 15, 30]) * rnd.uniform(0.8, 1.2), 2)}
        info.update({"name": n, "forge_name": n, "layout": "normal", "color_identity": [], "game_changer": False,
                     "legal_commander": True, "keywords": [], "usd": None, "mana_cost": "", "v": 2,
                     "fetched": 2 ** 40})
        card_db.cards[n.lower()] = info


def demo_edhrec(deck):
    rnd = random.Random(deck.commanders[0])
    cards = {n: {"inclusion": rnd.choice([2, 8, 20, 35, 55, 70]), "synergy": round(rnd.uniform(-0.1, 0.4), 2),
                 "list": "Top Cards"} for _, n in deck.cards if n.lower() not in ("mountain", "forest", "island")}
    for i in range(1, 16):
        cards[f"Demo Staple {i}"] = {"inclusion": rnd.randint(25, 80), "synergy": round(rnd.uniform(0, 0.5), 2),
                                     "list": "High Synergy Cards"}
    return {"url": "https://edhrec.com/", "decks": 4321, "cards": cards}
