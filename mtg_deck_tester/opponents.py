"""Pick a varied field of popular opponent decks.

Rules:
* popular decks, picked at random with more popular decks more likely (sites interleaved)
* decks you faced in your last few runs are much less likely to be picked again
* same bracket as your deck (decks without a bracket set are only used if needed)
* few colour-identity repeats: every identity gets one deck before any gets a second
* at most one or two decks with your commander, no duplicate commanders otherwise
* no copies of your own deck, only valid commanders, 98-101 cards
"""
import random
from collections import Counter

MAX_FETCHES = 80
COLORS = "WUBRG"


def identity_str(ident):
    return "".join(c for c in COLORS if c in ident) or "C"


def can_be_commander(info):
    if not info:
        return True  # unknown card: let Forge decide
    t = info["type_line"].split(" // ")[0].lower()
    o = (info.get("oracle") or "").lower()
    return ("legendary" in t and "creature" in t) or "can be your commander" in o or \
        "background" in t or ("legendary" in t and "spacecraft" in t)


def clean_commanders(deck, card_db):
    """Drop cards wrongly tagged as commander (they go back into the 99)."""
    keep, moved = [], []
    for c in deck.commanders:
        (keep if can_be_commander(card_db.get(c)) and len(keep) < 2 else moved).append(c)
    if moved:
        deck.cards += [(1, m) for m in moved]
    deck.commanders = keep
    return moved


def _identity(deck, card_db):
    ident = set()
    for c in deck.commanders:
        info = card_db.get(c)
        if info:
            ident |= set(info["color_identity"])
    return frozenset(ident)


def _overlap(a, b):
    sa = {n.lower() for n in a.all_names()}
    sb = {n.lower() for n in b.all_names()}
    return len(sa & sb) / max(1, min(len(sa), len(sb)))


def pick(sources, user_deck, user_identity, bracket, wanted, card_db, log, manual=(), recent=(), rng=None,
         value_target=None, value_tolerance=0.3):
    """value_target: your deck's value in EUR to match within value_tolerance, or None if value doesn't matter."""
    """sources: list of objects with .search(commanders, bracket) and .fetch(ref)."""
    picked = list(manual)
    ids = Counter({frozenset(user_identity): 1})
    for d in picked:
        ids[_identity(d, card_db)] += 1
    used_cmds = {tuple(sorted(c.lower() for c in user_deck.commanders))}
    used_cmds |= {tuple(sorted(c.lower() for c in d.commanders)) for d in picked}
    same_cmd_budget = 1 if wanted < 15 else 2

    # gather + interleave by popularity rank
    by_source = []
    for src in sources:
        try:
            cands = src.search(user_deck.commanders, bracket)
        except Exception as e:
            log(f"  {src.name} search failed: {e}")
            cands = []
        cands.sort(key=lambda c: (not c.from_commander_search, -c.views))
        for i, c in enumerate(cands):
            c.rank = i
        by_source.append((src, cands))
        log(f"  {src.name}: {len(cands)} candidate decks")
    # weighted random order: popular decks are more likely to come first, but every run differs
    rng = rng or random.Random()
    recent = set(recent)

    def order_key(c):
        weight = 1.0 / (c.rank + 15)
        if c.key in recent:
            weight *= 0.08  # faced recently: rarely picked again
        if c.from_commander_search:
            weight *= 3
        return rng.random() ** (1.0 / weight)
    pool = sorted(((order_key(c), n, c, src) for n, (src, cands) in enumerate(by_source) for c in cands),
                  key=lambda t: -t[0])
    n_recent = sum(1 for _, _, c, _ in pool if c.key in recent)
    if n_recent:
        log(f"  {n_recent} of these were in your recent runs and are less likely to be picked")

    cache, rejected, fetches = {}, set(), 0
    max_fetches = MAX_FETCHES + (40 if value_target else 0)

    def load(c, src):
        nonlocal fetches
        if c.key in cache:
            return cache[c.key]
        if fetches >= max_fetches:
            return None
        fetches += 1
        try:
            d = src.fetch(c.ref)
        except Exception as e:
            log(f"  skipped {c.name or c.ref}: {e}")
            d = None
        if d:
            try:
                card_db.resolve(d.all_names() if value_target else d.commanders)
            except Exception:
                pass
            if value_target:
                from .scryfall import deck_value
                d.value = deck_value(d, card_db)[0]
            moved = clean_commanders(d, card_db)
            if moved:
                log(f"  fixed {d.name}: {', '.join(moved)} is not a commander")
        cache[c.key] = d
        return d

    strict_passes = [(True, 1, value_tolerance), (True, 2, value_tolerance), (False, 2, value_tolerance),
                     (False, 3, max(value_tolerance, 0.5)), (False, 99, max(value_tolerance, 0.5)), (False, 99, None)]
    if not value_target:
        strict_passes = [p for p in strict_passes if p[2] is not None]
    warned_value = False
    for strict_bracket, cap, tol in strict_passes:
        if value_target and tol is None and not warned_value and len(picked) < wanted:
            log("Not enough decks close to your deck's value; also using decks with other values...")
            warned_value = True
        for _, _, c, src in pool:
            if len(picked) >= wanted:
                break
            if c.key in rejected or any(getattr(p, "_key", None) == c.key for p in picked):
                continue
            # cheap checks from search data before downloading
            if c.bracket is not None and bracket and int(c.bracket) != int(bracket):
                rejected.add(c.key)
                continue
            if c.colors is not None and ids[c.colors] >= cap and not c.from_commander_search:
                continue
            d = load(c, src)
            if d is None:
                rejected.add(c.key)
                continue
            if not d.commanders or not 98 <= d.size <= 101:
                rejected.add(c.key)
                continue
            if bracket and d.bracket is not None and int(d.bracket) != int(bracket):
                rejected.add(c.key)
                continue
            if bracket and d.bracket is None and strict_bracket:
                continue
            if value_target and tol is not None and abs(getattr(d, "value", 0) - value_target) > tol * value_target:
                continue
            if _overlap(d, user_deck) >= 0.9:
                log(f"  skipped {d.name}: looks like a copy of your deck")
                rejected.add(c.key)
                continue
            ident = _identity(d, card_db)
            cmd_key = tuple(sorted(x.lower() for x in d.commanders))
            if cmd_key == tuple(sorted(x.lower() for x in user_deck.commanders)):
                if same_cmd_budget <= 0:
                    rejected.add(c.key)
                    continue
                same_cmd_budget -= 1
            elif cmd_key in used_cmds:
                rejected.add(c.key)
                continue
            elif ids[ident] >= cap:
                continue
            d._key = c.key
            picked.append(d)
            used_cmds.add(cmd_key)
            ids[ident] += 1
            val = f", €{d.value:,.0f}" if getattr(d, "value", None) else ""
            log(f"  + {d.name} ({' & '.join(d.commanders)}, {identity_str(ident)}, "
                f"bracket {d.bracket or '?'}{val}, {d.source}, {d.views:,} views)")
        if len(picked) >= wanted:
            break
        if strict_bracket and cap == 2 and tol == value_tolerance and len(picked) < wanted:
            log("Not enough decks with a matching bracket; also using decks without a bracket set...")
    return picked[:wanted]
