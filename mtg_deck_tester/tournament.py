"""Swiss-style Commander tournament in pods of four, played by Forge's AI."""
import os
import queue
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict

from . import forge, demo

USER = "D01"


Cancelled = forge.Cancelled


def _swiss_pods(ids, points, history, rnd):
    if rnd == 1:
        order = ids[:]
        random.shuffle(order)
    else:
        order = sorted(ids, key=lambda d: (-points[d], random.random()))
    pods = [order[i:i + 4] for i in range(0, len(order), 4)]
    # light repair: swap to avoid exact repeat pods
    for i in range(len(pods) - 1):
        if frozenset(pods[i]) in history:
            pods[i][-1], pods[i + 1][0] = pods[i + 1][0], pods[i][-1]
    return pods


def run_tournament(user_deck, opponents, cfg, card_db, workdir, progress, cancel_event):
    """cfg keys: rounds, fast, workers, clock, strong_ai, forge_folder, demo."""
    decks = {USER: user_deck}
    for i, d in enumerate(opponents, 2):
        decks[f"D{i:02d}"] = d
    ids = list(decks)
    deck_dir = os.path.join(workdir, "decks")
    log_dir = os.path.join(workdir, "logs")
    os.makedirs(deck_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    for did, d in decks.items():
        forge.write_dck(d, did, card_db, os.path.join(deck_dir, f"{did}.dck"))

    cmd_sets = {did: set(d.commanders) | {(card_db.get(c) or {}).get("forge_name", c) for c in d.commanders}
                for did, d in decks.items()}
    card_sets = {}
    for did, d in decks.items():
        s = set()
        for n in d.all_names():
            s.add(n)
            info = card_db.get(n)
            if info:
                s.add(info["forge_name"])
        card_sets[did] = s

    rounds = cfg["rounds"]
    helper_box, jar = [None], None
    if not cfg.get("demo"):
        jar = forge.find_forge_jar(cfg["forge_folder"])
        helper_box[0] = forge.ensure_helper(jar, forge.find_java(), cfg["cache_dir"],
                                            log=lambda m: progress(0, 0, m))
    fast = cfg["fast"] or len(ids) < 8
    total = rounds * (1 if fast else len(ids) // 4)
    points = {d: 0.0 for d in ids}
    history, games, errors = set(), [], []
    done = 0
    strength = {d: random.uniform(-0.6, 0.6) for d in ids}
    opp_cycle = []
    lock = threading.Lock()

    workers = max(1, cfg.get("workers", 1))
    sessions = queue.Queue()
    all_sessions = []
    if helper_box[0]:
        for _ in range(workers):
            s = forge.ForgeSession(cfg["forge_folder"], helper_box[0], log_dir, log=lambda m: progress(done, total, m))
            all_sessions.append(s)
            sessions.put(s)
    mull = cfg.get("mulligan")  # e.g. "3,5,1,2" or ""
    prof_you, prof_opp = cfg.get("ai_profile_you", ""), cfg.get("ai_profile_opp", "")

    def specs(seats):
        return [f"{s}.dck|{prof_you if s == USER else prof_opp}|{mull if s == USER and mull else ''}" for s in seats]

    def play(rnd, pod_no, seats):
        if cancel_event.is_set():
            raise Cancelled()
        log_path = os.path.join(log_dir, f"round{rnd}_pod{pod_no}.log")
        if cfg.get("demo"):
            out = demo.fake_game(seats, decks, strength)
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(out)
        elif helper_box[0]:
            s = sessions.get()
            try:
                out = s.play(deck_dir, specs(seats), log_path, cfg["clock"], cfg.get("max_turns", 60),
                             cfg.get("stall_turns", 16), cfg.get("strong_ai", False), cancel_event)
            except Cancelled:
                raise
            except Exception as e:
                if s.games <= 1 and "Forge:" not in str(e):
                    # the helper doesn't work with this Forge version: fall back to plain sim mode
                    helper_box[0] = None
                    forge.disable_helper(jar)
                    progress(done, total, "The Forge helper failed with this Forge version; "
                                          "continuing in Forge's normal mode (no opening hands or mulligan rules).")
                    out = forge.run_pod(cfg["forge_folder"], deck_dir, [f"{x}.dck" for x in seats], cfg["clock"],
                                        log_path, cancel_event, cfg.get("strong_ai", False))
                else:
                    raise
            finally:
                sessions.put(s)
        else:
            out = forge.run_pod(cfg["forge_folder"], deck_dir, [f"{x}.dck" for x in seats], cfg["clock"], log_path,
                                cancel_event, cfg.get("strong_ai", False))
        return forge.parse_game(out, seats, cmd_sets, card_sets, focus=USER)

    for rnd in range(1, rounds + 1):
        if cancel_event.is_set():
            raise Cancelled()
        if fast:
            if len(opp_cycle) < 3:
                pool = [d for d in ids if d != USER]
                random.shuffle(pool)
                opp_cycle += [d for d in pool if d not in opp_cycle]
            pods = [[USER] + [opp_cycle.pop(0) for _ in range(3)]]
        else:
            pods = _swiss_pods(ids, points, history, rnd)
        for p in pods:
            random.shuffle(p)  # random seating
            history.add(frozenset(p))
        progress(done, total, f"Round {rnd}: {len(pods)} pod(s) at the table")

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(play, rnd, i + 1, p): (i + 1, p) for i, p in enumerate(pods)}
            for fut in as_completed(futs):
                pod_no, seats = futs[fut]
                try:
                    res = fut.result()
                except Cancelled:
                    raise
                except Exception as e:
                    errors.append(f"Round {rnd} pod {pod_no}: {e}")
                    with lock:
                        done += 1
                    progress(done, total, f"Round {rnd} pod {pod_no} failed: {str(e)[:200]}")
                    continue
                with lock:
                    for d, ps in res.players.items():
                        points[d] += ps.points
                    games.append({
                        "round": rnd, "pod": pod_no, "seats": seats, "winner": res.winner,
                        "draw": res.draw, "table_rounds": res.rounds, "duration_ms": res.duration_ms,
                        "killers": res.killers,
                        "timeline": res.timeline if USER in seats else [],
                        "players": {d: asdict(ps) for d, ps in res.players.items()},
                    })
                    done += 1
                if USER in seats:
                    me = res.players[USER]
                    msg = (f"Round {rnd}: you finished {_ord(me.place)} in your pod"
                           + (" (game timed out)" if res.draw else ""))
                else:
                    w = res.winner
                    msg = f"Round {rnd} pod {pod_no}: " + (f"{decks[w].name} won" if w else "draw")
                progress(done, total, msg)
        if errors and len(errors) >= max(3, total // 2) and not games:
            raise RuntimeError("Forge failed repeatedly:\n" + "\n".join(errors[:3]))

    for s in all_sessions:
        s.close()

    # standings
    stand = []
    for d in ids:
        places = [g["players"][d]["place"] for g in games if d in g["players"]]
        stand.append({"id": d, "name": decks[d].name, "points": points[d], "games": len(places),
                      "places": places, "avg_place": round(sum(places) / len(places), 2) if places else None,
                      "wins": sum(1 for p in places if p == 1)})
    stand.sort(key=lambda s: (-s["points"], s["avg_place"] or 9, -s["wins"]))
    for i, s in enumerate(stand, 1):
        s["rank"] = i
    return {
        "user_id": USER, "fast_mode": fast, "rounds": rounds, "games": games, "errors": errors,
        "standings": stand,
        "decks": {d: {"name": x.name, "commanders": x.commanders, "url": x.url,
                      "bracket": x.bracket, "source": x.source,
                      "identity": "".join(c for c in "WUBRG" if c in identity_of(x, card_db)) or "C"}
                  for d, x in decks.items()},
    }


def identity_of(deck, card_db):
    if getattr(deck, "identity_hint", None) and not any(card_db.get(c) for c in deck.commanders):
        return deck.identity_hint
    ident = set()
    for c in deck.commanders:
        info = card_db.get(c)
        if info:
            ident |= set(info["color_identity"])
    return ident


def _ord(n):
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")
