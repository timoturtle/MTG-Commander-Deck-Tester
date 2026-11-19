"""Goldfish simulation: plays a deck alone thousands of times to measure speed and consistency.

"Goldfishing" means playing without opponents. It answers questions Forge's AI can't: how often
the deck keeps a good hand, curves out, casts its commander on time, and how fast it can
assemble each of its combos when it plays towards them deliberately (ramp first, tutors fetch
missing pieces). It is a statistical estimate: no opponents, no interaction, card effects are
simplified to ramp, card draw, tutors and the combo pieces themselves.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

BASICS = {"plains", "island", "swamp", "mountain", "forest", "wastes"}
TYPES = ("creature", "artifact", "enchantment", "instant", "sorcery", "planeswalker", "battle", "land")
WORDNUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "x": 2}
MAX_TURN = 10        # combos are measured up to here
KILL_TURN = 15       # the solo win check runs this long
OPP_LIFE = 40


def norm(name):
    return name.split(" // ")[0].strip().lower()


@dataclass
class Card:
    name: str
    cmc: int = 3
    land: bool = False
    tapped: bool = False
    mana: int = 0             # mana it adds every turn once on the battlefield
    haste_mana: bool = True   # usable the turn it is cast (artifacts) or next turn (creatures)
    landramp: int = 0         # lands it puts onto the battlefield
    land_to_hand: bool = False
    tutor: str | None = None  # None, "any" or a card type
    tutor_top: bool = False
    draw: int = 0
    engine: bool = False
    types: frozenset = field(default_factory=frozenset)
    # win check
    power: int = 0
    haste: bool = False
    infect: bool = False
    toxic: int = 0
    drain_once: int = 0      # non-combat damage / life loss for each opponent when cast
    drain_turn: int = 0      # non-combat damage / life loss for each opponent per turn on the battlefield
    punish_draw: int = 0     # damage to an opponent for each card they draw (Nekusar, Underworld Dreams...)
    opp_draws: int = 0       # cards each opponent draws when this is cast (wheels, group draw)
    opp_draw_turn: int = 0   # extra cards each opponent draws every turn while on the battlefield
    mill_once: int = 0
    mill_turn: int = 0
    alt_win: bool = False


def model(name, info):
    if not info:
        base = norm(name).replace("snow-covered ", "")
        return Card(name, cmc=0 if base in BASICS else 3, land=base in BASICS)
    tl = (info.get("type_line") or "").split(" // ")[0].lower()
    o = (info.get("oracle") or "").split(" // ")[0].lower()
    types = frozenset(t for t in TYPES if t in tl)
    c = Card(name, cmc=int(round(info.get("cmc") or 0)), types=types)
    _win_traits(c, info, o)
    if "land" in types:
        c.land, c.cmc = True, 0
        c.tapped = ("enters tapped" in o or "enters the battlefield tapped" in o) and "unless" not in o
        return c
    permanent = bool(types & {"creature", "artifact", "enchantment", "planeswalker", "battle"})
    m = re.search(r"\badd ((?:\{[^}]+\})+)", o)
    if permanent and m and "{t}" in o:
        c.mana = min(3, len(re.findall(r"\{[^}]+\}", m.group(1))))
    elif permanent and re.search(r"\{t\}[^.]*: add (one|two) mana", o):
        c.mana = 2 if "add two mana" in o else 1
    if c.mana and "creature" in types:
        c.haste_mana = False
    lm = re.search(r"search your library for (?:up to (\w+)|an?|two) [^.]*?(?:basic )?(?:land|forest|island|swamp|mountain|plains)"
                   r"[^.]*?onto the battlefield", o)
    if lm and not permanent or (lm and "when" in o and "enters" in o):
        n = WORDNUM.get((lm.group(1) or "a").lower(), 1)
        c.landramp = min(2, n)
        c.land_to_hand = "into your hand" in o or "the other into your hand" in o
    tm = re.search(r"search your library for an? ((?:\w+ )?(?:or \w+ )?)card", o)
    if tm and "land" not in tm.group(1):
        word = tm.group(1).strip()
        c.tutor = "any" if not word else next((t for t in TYPES if t in word), "any")
        c.tutor_top = "on top" in o
    dm = re.search(r"draws? (a|one|two|three|four|five|x) cards?", o)
    if dm:
        n = WORDNUM.get(dm.group(1), 1)
        if permanent and re.search(r"(whenever|at the beginning of)[^.]*draw", o):
            c.engine = True
        elif not permanent or "when" in o:
            c.draw = n
    return c


def _num(s, default=2):
    s = (s or "").strip().lower()
    return int(s) if s.isdigit() else WORDNUM.get(s, default)


def _win_traits(c, info, o):
    """Non-combat and combat ways a card helps the deck win on its own."""
    p = str(info.get("power") or "")
    c.power = int(p) if p.isdigit() else (2 if p else 0)
    kw = " ".join(info.get("keywords") or []).lower()
    c.haste = "haste" in kw or "haste" in o.split("\n")[0]
    c.infect = "infect" in kw
    tm = re.search(r"toxic (\d+)", o)
    c.toxic = int(tm.group(1)) if tm else 0
    repeat = bool(re.search(r"(whenever|at the beginning of)", o))
    dm = re.search(r"each opponent loses (\w+) life|deals (\w+) damage to each opponent|"
                   r"each opponent loses x life", o)
    if dm:
        n = _num(dm.group(1) or dm.group(2) or "x", default=3)
        if repeat and c.types & {"creature", "artifact", "enchantment", "planeswalker"}:
            c.drain_turn = min(n, 3)
        else:
            c.drain_once = min(n, 10)
    pm = re.search(r"whenever an opponent draws a card[^.]*?(?:deals (\w+) damage|loses (\w+) life)", o)
    if pm:
        c.punish_draw = _num(pm.group(1) or pm.group(2), default=1)
    elif repeat and c.types & {"creature", "artifact", "enchantment", "planeswalker"}:
        tm2 = re.search(r"deals (\w+) damage to (?:target opponent|target player|any target|that player)", o)
        if tm2 and not dm:
            c.drain_turn = max(c.drain_turn, round(_num(tm2.group(1), default=1) / 3))  # one opponent per trigger
    wm = re.search(r"each player (?:discards their hand, then )?draws (\w+) cards?|"
                   r"each opponent draws (\w+) cards?|each player shuffles their hand[^.]*draws (\w+)", o)
    if wm:
        c.opp_draws = _num(wm.group(1) or wm.group(2) or wm.group(3), default=3)
    elif re.search(r"each player discards their hand, then draws cards equal", o):
        c.opp_draws = 6
    if re.search(r"(that player|each player|each opponent) draws an additional card", o):
        c.opp_draw_turn = 1
    mm = re.search(r"(?:each opponent|target player|target opponent) mills (\w+)", o)
    if mm:
        n = _num(mm.group(1), default=3)
        if repeat and c.types & {"creature", "artifact", "enchantment", "planeswalker"}:
            c.mill_turn = min(n, 10)
        else:
            c.mill_once = min(n, 30)
    c.alt_win = "you win the game" in o


class Goldfish:
    def __init__(self, deck, card_db, combos=(), focus=()):
        self.cards = []
        for q, n in deck.cards:
            m = model(n, card_db.get(n) if card_db else None)
            self.cards += [m] * int(q)
        self.cmds = [model(n, card_db.get(n) if card_db else None) for n in deck.commanders]
        cmd_keys = {norm(n): i for i, n in enumerate(deck.commanders)}
        index = {}
        for i, c in enumerate(self.cards):
            index.setdefault(norm(c.name), []).append(i)
        # combos as lists of piece requirements: ("lib", {card indices}) or ("cmd", commander index)
        self.combos = []
        for combo in combos:
            reqs, ok, needs_bf = [], True, []
            for p in combo["pieces"]:
                k = norm(p["name"])
                if k in cmd_keys:
                    reqs.append(("cmd", cmd_keys[k]))
                elif k in index:
                    reqs.append(("lib", frozenset(index[k])))
                else:
                    ok = False
                    break
                needs_bf.append("B" in (p.get("zones") or ["B"]))
            if ok and reqs:
                self.combos.append({"reqs": reqs, "bf": needs_bf, "extra": combo.get("mana_value_needed", 0)})
        # focus cards: card indices (or the commander) to follow
        self.focus = {}
        for f in focus:
            k = norm(f)
            if k in cmd_keys:
                self.focus[f] = ("cmd", cmd_keys[k])
            elif k in index:
                self.focus[f] = ("lib", frozenset(index[k]))
        # pieces used from hand (instants, sorceries...) are held until the combo turn
        self.hold = set()
        for combo in self.combos:
            for (kind, ref), b in zip(combo["reqs"], combo["bf"]):
                if kind == "lib" and not b:
                    self.hold |= ref

    # ------------------------------------------------------------------ one game
    def _game(self, rng):
        C = self.cards
        lib = list(range(len(C)))
        mulls = 0
        while True:
            rng.shuffle(lib)
            hand = lib[:7]
            lands = sum(1 for i in hand if C[i].land)
            cheap = any((C[i].mana or C[i].landramp) and C[i].cmc <= 2 for i in hand)
            if 3 <= lands <= 5 or (lands == 2 and cheap) or mulls >= 2:
                break
            mulls += 1
        rest = lib[7:]
        bottom_n = max(0, mulls - 1)  # the first mulligan is free in multiplayer Commander
        if bottom_n:
            n_lands = sum(1 for i in hand if C[i].land)
            key = (lambda i: (0 if C[i].land else 1)) if n_lands > 4 else (lambda i: (1 if C[i].land else 0, -C[i].cmc))
            hand.sort(key=key)
            rest += hand[:bottom_n]
            hand = hand[bottom_n:]
        kept_lands = sum(1 for i in hand if C[i].land)
        library = rest  # draw from the front
        hand = set(hand)
        bf = set()
        cmd_cast = [False] * len(self.cmds)
        sources = []          # (amount, first usable turn)
        engines = 0
        opp = [{"life": OPP_LIFE, "poison": 0, "cmd": 0, "lib": 92} for _ in range(3)]
        attackers = []        # [power, infect, toxic, is_commander, first attack turn]
        drain_engines = mill_engines = punishers = extra_draws = 0
        dmg = {"combat": 0, "commander": 0, "noncombat": 0, "poison": 0, "mill": 0}

        def alive():
            return [o for o in opp if o["life"] > 0 and o["poison"] < 10 and o["cmd"] < 21 and o["lib"] >= 0]

        res = {"kill": None, "altwin": None, "dmg": dmg,
               "mulls": mulls, "kept": 7 - bottom_n, "kept_lands": kept_lands, "first_play": None,
               "t1": False, "t2": False, "cmd_turn": None, "lands_t3": 0, "mana": {}, "combo": [None] * len(self.combos),
               "lands_seen": 0}
        seen = 7
        lands_seen = kept_lands
        now = [0]
        f_seen, f_cast = {}, {}
        for fname, (kind, ref) in self.focus.items():
            if kind == "cmd" or hand & ref:
                f_seen[fname] = 0  # commander or in the opening hand
        res["f_seen"], res["f_cast"] = f_seen, f_cast

        def note_seen(i):
            for fname, (kind, ref) in self.focus.items():
                if kind == "lib" and i in ref and fname not in f_seen:
                    f_seen[fname] = now[0]

        def draw(n):
            nonlocal seen, lands_seen
            for _ in range(n):
                if library:
                    i = library.pop(0)
                    hand.add(i)
                    note_seen(i)
                    seen += 1
                    if seen <= 13 and C[i].land:
                        lands_seen += 1

        def have(req):
            kind, ref = req
            if kind == "cmd":
                return True
            return any(i in hand or i in bf for i in ref)

        def piece_cost(req, needs_bf):
            kind, ref = req
            if kind == "cmd":
                return 0 if cmd_cast[ref] else self.cmds[ref].cmc
            if any(i in bf for i in ref):
                return 0
            return min(C[i].cmc for i in ref if i in hand)

        def missing_pieces():
            best = None
            for k, combo in enumerate(self.combos):
                if res["combo"][k] is not None:
                    continue
                miss = [r for r in combo["reqs"] if not have(r)]
                if best is None or len(miss) < len(best):
                    best = miss
            return best or []

        for t in range(1, KILL_TURN + 1):
            now[0] = t
            draw(1 + engines)
            # land drop (untapped first)
            lands_in_hand = [i for i in hand if C[i].land]
            if lands_in_hand:
                i = min(lands_in_hand, key=lambda j: C[j].tapped)
                hand.discard(i)
                bf.add(i)
                sources.append((1, t + 1 if C[i].tapped else t))
                if t <= 3:
                    res["lands_t3"] += 1
            mana = sum(a for a, ready in sources if ready <= t)
            res["mana"][t] = mana
            casted_this_turn = False
            while True:
                # 1) can a combo be completed right now?
                for k, combo in enumerate(self.combos):
                    if res["combo"][k] is None and all(have(r) for r in combo["reqs"]):
                        cost = max(sum(piece_cost(r, b) for r, b in zip(combo["reqs"], combo["bf"])), combo["extra"])
                        if cost <= mana:
                            res["combo"][k] = t
                # 2) cast the most useful affordable card
                miss = missing_pieces()
                miss_ids = set()
                for kind, ref in miss:
                    if kind == "lib":
                        miss_ids |= ref
                want_ids = set()
                for k, combo in enumerate(self.combos):
                    if res["combo"][k] is None:
                        for (kind, ref), b in zip(combo["reqs"], combo["bf"]):
                            if kind == "lib" and b:
                                want_ids |= ref

                def prio(i):
                    c = C[i]
                    if (c.mana or c.landramp) and t <= 6:
                        return 0
                    if c.tutor and miss_ids:
                        return 1
                    if i in want_ids:
                        return 2
                    if c.draw or c.engine:
                        return 4
                    if c.punish_draw or (c.opp_draws and punishers):
                        return 2.5
                    if c.power >= 2 or c.drain_turn or c.mill_turn or c.drain_once or c.mill_once:
                        return 3.5
                    return 5
                options = [(prio(i), -C[i].cmc, i) for i in hand
                           if not C[i].land and C[i].cmc <= mana and i not in self.hold]
                for ci, cm in enumerate(self.cmds):
                    if not cmd_cast[ci] and cm.cmc <= mana:
                        options.append((3, -cm.cmc, ("cmd", ci)))
                if not options:
                    break
                _, _, pick = min(options, key=lambda o: (o[0], o[1]))
                if isinstance(pick, tuple):
                    ci = pick[1]
                    mana -= self.cmds[ci].cmc
                    cmd_cast[ci] = True
                    if res["cmd_turn"] is None:
                        res["cmd_turn"] = t
                    for fname, (kind, ref) in self.focus.items():
                        if kind == "cmd" and ref == ci and fname not in f_cast:
                            f_cast[fname] = t
                    c = self.cmds[ci]
                else:
                    c = C[pick]
                    hand.discard(pick)
                    for fname, (kind, ref) in self.focus.items():
                        if kind == "lib" and pick in ref and fname not in f_cast:
                            f_cast[fname] = t
                    mana -= c.cmc
                    if c.types & {"creature", "artifact", "enchantment", "planeswalker", "battle"} or \
                            not c.types or pick in want_ids:
                        bf.add(pick)
                casted_this_turn = True
                if res["first_play"] is None:
                    res["first_play"] = t
                if c.mana:
                    ready = t if c.haste_mana else t + 1
                    sources.append((c.mana, ready))
                    if ready <= t:
                        mana += c.mana
                if c.landramp:
                    for _ in range(c.landramp):
                        sources.append((1, t + 1))
                    if c.land_to_hand:
                        j = next((j for j in library if C[j].land), None)
                        if j is not None:
                            library.remove(j)
                            hand.add(j)
                if c.tutor:
                    target = None
                    for j in library:
                        if j in miss_ids and (c.tutor == "any" or c.tutor in C[j].types):
                            target = j
                            break
                    if target is not None:
                        library.remove(target)
                        if c.tutor_top:
                            library.insert(0, target)
                        else:
                            hand.add(target)
                            note_seen(target)
                if c.draw:
                    draw(c.draw)
                if c.engine:
                    engines += 1
                if "creature" in c.types and (c.power or c.infect):
                    attackers.append([c.power, c.infect, c.toxic, isinstance(pick, tuple), t if c.haste else t + 1])
                punishers += c.punish_draw
                extra_draws += c.opp_draw_turn
                for o in alive():
                    if c.drain_once:
                        o["life"] -= c.drain_once
                        dmg["noncombat"] += c.drain_once
                    if c.opp_draws:
                        o["lib"] -= c.opp_draws
                        if punishers:
                            o["life"] -= punishers * c.opp_draws
                            dmg["noncombat"] += punishers * c.opp_draws
                    if c.mill_once:
                        o["lib"] -= c.mill_once
                        dmg["mill"] += c.mill_once
                drain_engines += c.drain_turn
                mill_engines += c.mill_turn
            # alt-win cards: first turn one could be cast
            if res["altwin"] is None and any(C[i].alt_win and C[i].cmc <= res["mana"].get(t, 0) for i in hand | bf):
                res["altwin"] = t
            # combat (no blockers) and per-turn engines
            for a in attackers:
                if a[4] > t:
                    continue
                targets = alive()
                if not targets:
                    break
                o = min(targets, key=lambda x: (x["poison"] * 4 if a[1] else x["life"]))
                if a[1]:
                    o["poison"] += a[0]
                    dmg["poison"] += a[0]
                else:
                    o["life"] -= a[0]
                    dmg["commander" if a[3] else "combat"] += a[0]
                    if a[2]:
                        o["poison"] += a[2]
                        dmg["poison"] += a[2]
                if a[3]:
                    o["cmd"] += a[0]
            for o in alive():
                if drain_engines:
                    o["life"] -= drain_engines
                    dmg["noncombat"] += drain_engines
                if punishers:  # every opponent draws once per turn, plus extra draws (Nekusar...)
                    o["life"] -= punishers * (1 + extra_draws)
                    dmg["noncombat"] += punishers * (1 + extra_draws)
                o["lib"] -= 1 + extra_draws + mill_engines
                dmg["mill"] += mill_engines
            if res["kill"] is None and not alive():
                res["kill"] = t
            if t == 1:
                res["t1"] = casted_this_turn
            if t == 2:
                res["t2"] = casted_this_turn
        res["lands_seen"] = lands_seen
        return res

    # ------------------------------------------------------------------ many games
    def run(self, n=5000, seed=None, win_combo_idx=()):
        rng = random.Random(seed)
        games = [self._game(rng) for _ in range(n)]
        pct = lambda k: round(100 * k / n, 1)

        def by_turn(turns):
            out = {f"t{t}": pct(sum(1 for x in turns if x is not None and x <= t)) for t in (4, 6, 8, 10)}
            done = sorted(x for x in turns if x is not None)
            out["median"] = done[len(done) // 2] if len(done) * 2 >= n else None  # None = after turn 10
            return out

        combo_stats = [by_turn([g["combo"][k] for g in games]) for k in range(len(self.combos))]

        def kill_by_turn(turns):
            out = {f"t{t}": pct(sum(1 for x in turns if x is not None and x <= t)) for t in (6, 8, 10, 12, 15)}
            done = sorted(x for x in turns if x is not None)
            out["median"] = done[len(done) // 2] if len(done) * 2 >= n else None
            return out
        totals = {k: sum(g["dmg"][k] for g in games) for k in ("combat", "commander", "noncombat", "poison", "mill")}
        all_dmg = sum(totals.values()) or 1
        win = {"solo_kill": kill_by_turn([g["kill"] for g in games]),
               "sources": {k: round(100 * v / all_dmg) for k, v in totals.items() if v},
               "altwin": kill_by_turn([g["altwin"] for g in games]) if any(g["altwin"] for g in games) else None,
               "alt_win_cards": sorted({c.name for c in self.cards if c.alt_win})}
        any_turn = [min((x for x in g["combo"] if x is not None), default=None) for g in games]
        cmd_cmc = min((c.cmc for c in self.cmds), default=0)
        return {
            "games": n,
            "keep7": pct(sum(1 for g in games if g["mulls"] == 0)),
            "avg_mulligans": round(sum(g["mulls"] for g in games) / n, 2),
            "avg_kept_lands": round(sum(g["kept_lands"] for g in games) / n, 2),
            "t1_play": pct(sum(1 for g in games if g["t1"])),
            "t2_play": pct(sum(1 for g in games if g["t2"])),
            "screw": pct(sum(1 for g in games if g["lands_t3"] < 3)),
            "flood": pct(sum(1 for g in games if g["lands_seen"] >= 8)),
            "cmd_on_curve": pct(sum(1 for g in games if g["cmd_turn"] is not None and g["cmd_turn"] <= max(1, cmd_cmc))),
            "cmd_by_t4": pct(sum(1 for g in games if g["cmd_turn"] is not None and g["cmd_turn"] <= 4)),
            "cmd_avg_turn": round(sum(g["cmd_turn"] for g in games if g["cmd_turn"]) /
                                  max(1, sum(1 for g in games if g["cmd_turn"])), 1),
            "avg_mana_t4": round(sum(g["mana"].get(4, 0) for g in games) / n, 1),
            "avg_mana_t6": round(sum(g["mana"].get(6, 0) for g in games) / n, 1),
            "combo_any": by_turn(any_turn) if self.combos else None,
            "combo_each": combo_stats,
            "simulated_combos": len(self.combos),
            "win": win,
            "focus": {f: {"seen_opening": pct(sum(1 for g in games if g["f_seen"].get(f) == 0)),
                          "seen_by_t4": pct(sum(1 for g in games if g["f_seen"].get(f, 99) <= 4)),
                          "seen_by_t8": pct(sum(1 for g in games if g["f_seen"].get(f, 99) <= 8)),
                          "cast_by_t8": pct(sum(1 for g in games if g["f_cast"].get(f, 99) <= 8)),
                          "avg_cast_turn": round(sum(g["f_cast"][f] for g in games if f in g["f_cast"]) /
                                                 max(1, sum(1 for g in games if f in g["f_cast"])), 1)
                          if any(f in g["f_cast"] for g in games) else None}
                      for f in self.focus},
            "win_any": kill_by_turn([min([x for x in [g["kill"]] + [g["combo"][k] for k in win_combo_idx]
                                         if x is not None], default=None) for g in games]),
        }


def chance_holding(k, deck_size=99, seen=13):
    """Probability of having seen at least one of k copies after `seen` cards (hypergeometric)."""
    if k <= 0:
        return 0.0
    p_none = 1.0
    for i in range(seen):
        p_none *= max(0.0, (deck_size - k - i) / (deck_size - i))
    return 1 - p_none
