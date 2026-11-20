"""Pick a random field of opponent decks, like sitting down at random tables.

Rules:
* random decks from a large pool of public decks; colours and commanders play no role
* same bracket as your deck (decks without a bracket set are only used if needed)
* optional: deck value within ±30% of yours
* decks you faced in your last 3 runs are only used if nothing else is left
* no copies of your own deck, only valid commanders, 98-101 cards, no deck twice
"""
import random

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
    rng = rng or random.Random()
    recent = set(recent)
    picked = list(manual)

    pool = []
    for src in sources:
        try:
            cands = src.search(user_deck.commanders, bracket)
        except Exception as e:
            log(f"  {src.name} search failed: {e}")
            cands = []
        log(f"  {src.name}: {len(cands)} candidate decks")
        pool += [(c, src) for c in cands]
    rng.shuffle(pool)
    # uniform random order; decks from your last runs go to the back of the queue
    pool.sort(key=lambda cs: cs[0].key in recent)
    n_recent = sum(1 for c, _ in pool if c.key in recent)
    if n_recent:
        log(f"  {n_recent} of these were in your recent runs and are only used if needed")

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
                card_db.cheapest(d.all_names(), 3.0)  # the expensive cards decide the value
                d.value = deck_value(d, card_db)[0]
            moved = clean_commanders(d, card_db)
            if moved:
                log(f"  fixed {d.name}: {', '.join(moved)} is not a commander")
        cache[c.key] = d
        return d

    # passes relax the rules step by step only if not enough decks were found
    passes = [(True, value_tolerance), (False, value_tolerance)]
    if value_target:
        passes += [(False, max(value_tolerance, 0.5)), (False, None)]
    for strict_bracket, tol in passes:
        if len(picked) >= wanted:
            break
        if not strict_bracket and tol == value_tolerance:
            log("Not enough decks with a bracket set; also using decks without one...")
        if value_target and tol is None:
            log("Not enough decks close to your deck's value; also using decks with other values...")
        for c, src in pool:
            if len(picked) >= wanted:
                break
            if c.key in rejected or any(getattr(p, "_key", None) == c.key for p in picked):
                continue
            if c.bracket is not None and bracket and int(c.bracket) != int(bracket):
                rejected.add(c.key)
                continue
            d = load(c, src)
            if d is None or not d.commanders or not 98 <= d.size <= 101:
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
            d._key = c.key
            picked.append(d)
            val = f", €{d.value:,.0f}" if getattr(d, "value", None) else ""
            log(f"  + {d.name} ({' & '.join(d.commanders)}, {identity_str(_identity(d, card_db))}, "
                f"bracket {d.bracket or '?'}{val}, {d.source})")
    return picked[:wanted]
