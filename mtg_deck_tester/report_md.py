"""Markdown report you can keep or share."""


def _ord(n):
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


def _c(s):
    """Make text safe inside a Markdown table cell."""
    return str(s).replace("|", "\\|").replace("\n", " ")


def to_markdown(rep):
    r, a = rep["results"], rep["analysis"]
    me = next(s for s in r["standings"] if s["id"] == "D01")
    out = [f"# Test tournament: {rep['deck']['name'] if rep['deck']['name'] != 'Your deck' else ' & '.join(rep['deck']['commanders'])}", "",
           f"Bracket {rep['bracket']} · {len(r['standings'])} decks · {r['rounds']} rounds · "
           f"{'your pods only' if r['fast_mode'] else 'full Swiss tournament'} · {rep['created']}", ""]
    if not r["fast_mode"]:
        out.append(f"**Final standing: {_ord(me['rank'])} of {len(r['standings'])}** ({me['points']:g} points)")
    out.append(f"**Pod finishes:** {', '.join(_ord(p) for p in me['places'])} "
               f"(average {me['avg_place']}, {me['wins']} win(s))")
    out += ["", "## Rounds", "", "| Round | Place | Opponents | How it ended |", "|---|---|---|---|"]
    for g in sorted([g for g in r["games"] if "D01" in g["players"]], key=lambda g: g["round"]):
        p = g["players"]["D01"]
        opps = _c(", ".join(r["decks"][s]["name"] for s in g["seats"] if s != "D01"))
        how = "won" if p["won"] else ("time limit" if g["draw"] and not p["eliminated"] else p["loss_reason"])
        out.append(f"| {g['round']} | {_ord(p['place'])} | {opps} | {_c(how)} |")
    out += ["", "## Weak points", ""]
    out += [f"- **{w['title']}** – {w['detail']}" for w in a["weak_points"]] or ["- None stood out."]
    if a["strengths"]:
        out += ["", "## Strengths", ""] + [f"- {s}" for s in a["strengths"]]
    out += ["", "## Suggestions", ""] + [f"- {s}" for s in a["suggestions"]]
    if a["cut_candidates"]:
        out += ["", "**Cards to reconsider (never cast in testing):** " +
                ", ".join(c["card"] for c in a["cut_candidates"])]
    if a["add_candidates"]:
        out += ["", "**Popular in similar decks, not in yours:** " +
                ", ".join(f"{c['card']} ({c['in_decks']})" for c in a["add_candidates"])]
    if rep.get("ai_text"):
        out += ["", "## AI coach", "", rep["ai_text"]]
    out += ["", "## Standings", "", "| # | Deck | Points | Pod finishes |", "|---|---|---|---|"]
    for s in r["standings"]:
        out.append(f"| {s['rank']} | {_c(s['name'])}{' (you)' if s['id']=='D01' else ''} | {s['points']:g} | "
                   f"{' '.join(str(p) for p in s['places'])} |")
    out += ["", "## Opponents", ""]
    for k, d in r["decks"].items():
        if k != "D01":
            out.append(f"- [{d['name']}]({d['url']}) – {' & '.join(d['commanders'])} ({d.get('identity', '?')}), "
                       f"bracket {d['bracket'] or '?'}, {d.get('source', '')}")
    E = a.get("early_game")
    if E and E["n"]:
        out += ["", "## Summary: opening hands and early plays", "",
                f"- Non-land play on your turn 1: **{E['t1_play']} of {E['t1_games']}** games",
                f"- Non-land play on your turn 2: **{E['t2_play']} of {E['t2_games']}** games",
                f"- Non-land play on both turns: **{E['both']} of {E['n']}** games",
                f"- Average kept hand: {E['avg_kept']} cards"
                + (f", {E['avg_lands_in_hand']} lands" if E["avg_lands_in_hand"] is not None else ""),
                "", "| Round | Place | Kept opening hand | Turn 1 | Turn 2 |", "|---|---|---|---|---|"]

        def play(c):
            return "didn't get this turn" if c is None else ("No" if not c else "Yes: " + ", ".join(c))
        for r in E["games"]:
            hand = f"{r['hand_text']} ({r['kept']} cards)" if r["hand"] else f"not recorded ({r['kept'] or '?'} cards)"
            out.append(f"| {r['round']} | {_ord(r['place'])} | {_c(hand)} | {_c(play(r['t1']))} | {_c(play(r['t2']))} |")
    return "\n".join(out) + "\n"
