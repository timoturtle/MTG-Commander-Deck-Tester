"""PDF version of the report, readable on phones, tablets and computers."""
import os
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from . import APP_NAME

INK = colors.HexColor("#1C2033")
MUTED = colors.HexColor("#5B6478")
BLUE = colors.HexColor("#2F6FDE")
LINE = colors.HexColor("#D5DBE3")
PANEL = colors.HexColor("#EEF1F5")
ME = colors.HexColor("#E3ECFC")
BAD = colors.HexColor("#B4372F")
BAD_BG = colors.HexColor("#F7F0EF")
GOOD = colors.HexColor("#2E7D4F")
PLACE = {1: colors.HexColor("#C59A1C"), 2: colors.HexColor("#8C96A3"),
         3: colors.HexColor("#A6693A"), 4: colors.HexColor("#4E566A")}

# Fonts installed with the operating system (nothing is bundled). Falls back to Helvetica.
FONT_CANDIDATES = [
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    (os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf"),
     os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arialbd.ttf")),
    (os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeui.ttf"),
     os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeuib.ttf")),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]
_FONT = None


def _fonts():
    global _FONT
    if _FONT:
        return _FONT
    for reg, bold in FONT_CANDIDATES:
        if os.path.exists(reg) and os.path.exists(bold):
            try:
                pdfmetrics.registerFont(TTFont("Body", reg))
                pdfmetrics.registerFont(TTFont("Body-Bold", bold))
                pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold",
                                              italic="Body", boldItalic="Body-Bold")
                face = pdfmetrics.getFont("Body").face
                _FONT = ("Body", "Body-Bold", set(face.charToGlyph.keys()))
                return _FONT
            except Exception:
                continue
    _FONT = ("Helvetica", "Helvetica-Bold", None)
    return _FONT


def _clean(s):
    """Drop characters the font can't draw (emoji etc.) so they don't show as boxes."""
    s = str(s if s is not None else "")
    glyphs = _fonts()[2]
    if glyphs is None:
        return "".join(ch for ch in s if ord(ch) < 256).strip()
    return "".join(ch for ch in s if ord(ch) in glyphs or ch in "\n\t").strip()


def t(s):
    return escape(_clean(s))


def ordinal(n):
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


class Badges(Flowable):
    """Row of coloured place circles (gold, silver, bronze, grey)."""

    def __init__(self, places, size=11, gap=3):
        super().__init__()
        self.places, self.size, self.gap = [int(p) for p in places], size, gap

    def wrap(self, *_):
        return len(self.places) * (self.size + self.gap), self.size

    def draw(self):
        c, r = self.canv, self.size / 2
        for i, p in enumerate(self.places):
            x = i * (self.size + self.gap) + r
            c.setFillColor(PLACE.get(p, PLACE[4]))
            c.circle(x, r, r, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont(_fonts()[1], self.size * 0.62)
            c.drawCentredString(x, r - self.size * 0.22, str(p))


def _styles():
    reg, bold, _ = _fonts()
    base = dict(fontName=reg, textColor=INK, fontSize=9.5, leading=13)
    return {
        "body": ParagraphStyle("body", **base),
        "small": ParagraphStyle("small", **dict(base, fontSize=8, leading=10.5, textColor=MUTED)),
        "cell": ParagraphStyle("cell", **dict(base, fontSize=8.5, leading=11)),
        "cellb": ParagraphStyle("cellb", **dict(base, fontName=bold, fontSize=8.5, leading=11)),
        "cellr": ParagraphStyle("cellr", **dict(base, fontSize=8.5, leading=11, alignment=TA_RIGHT)),
        "cellc": ParagraphStyle("cellc", **dict(base, fontSize=8.5, leading=11, alignment=TA_CENTER)),
        "th": ParagraphStyle("th", **dict(base, fontName=bold, fontSize=8.5, leading=11)),
        "kicker": ParagraphStyle("kicker", **dict(base, fontSize=8.5, textColor=MUTED)),
        "title": ParagraphStyle("title", **dict(base, fontName=bold, fontSize=22, leading=26, spaceBefore=2)),
        "h2": ParagraphStyle("h2", **dict(base, fontName=bold, fontSize=13.5, leading=17, textColor=BLUE,
                                          spaceBefore=14, spaceAfter=5, keepWithNext=1)),
        "h3": ParagraphStyle("h3", **dict(base, fontName=bold, fontSize=11, leading=14, spaceBefore=8,
                                          spaceAfter=2, keepWithNext=1)),
        "big": ParagraphStyle("big", **dict(base, fontName=bold, fontSize=26, leading=28)),
        "bullet": ParagraphStyle("bullet", **dict(base, leftIndent=12, bulletIndent=2, spaceAfter=2)),
    }


def _table(rows, widths, header=True, highlight_rows=()):
    tb = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("LINEBELOW", (0, 1 if header else 0), (-1, -1), 0.5, LINE),
          ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if header:
        st.append(("LINEBELOW", (0, 0), (-1, 0), 1.2, INK))
    for r in highlight_rows:
        st.append(("BACKGROUND", (0, r), (-1, r), ME))
    tb.setStyle(TableStyle(st))
    return tb


def _md_flowables(text, S, width):
    """Small Markdown renderer for the Claude coaching notes."""
    out, table = [], []

    def inline(s):
        s = t(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        return re.sub(r"`(.+?)`", r"\1", s)

    def flush_table():
        if not table:
            return
        n = max(len(r) for r in table)
        rows = [[Paragraph(inline(c), S["th"] if i == 0 else S["cell"]) for c in r + [""] * (n - len(r))]
                for i, r in enumerate(table)]
        out.append(_table(rows, [width / n] * n))
        out.append(Spacer(1, 4))
        table.clear()

    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|"):
            if not re.match(r"^\|[\s:|-]+\|$", s):
                table.append([c.strip() for c in s.strip("|").split("|")])
            continue
        flush_table()
        if not s:
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", s)
        if m:
            out.append(Paragraph(inline(m.group(2)), S["h3"]))
        elif re.match(r"^[-*]\s+", s):
            out.append(Paragraph(inline(re.sub(r"^[-*]\s+", "", s)), S["bullet"], bulletText="•"))
        elif re.match(r"^\d+[.)]\s+", s):
            num = re.match(r"^(\d+)", s).group(1)
            out.append(Paragraph(inline(re.sub(r"^\d+[.)]\s+", "", s)), S["bullet"], bulletText=num + "."))
        else:
            out.append(Paragraph(inline(s), S["body"]))
    flush_table()
    return out


METRICS = [("place", "Average pod finish", False), ("lands_t4", "Lands by your turn 4", True),
           ("first_spell", "First spell (your turn)", False), ("commander_turn", "Commander cast (your turn)", False),
           ("damage_dealt", "Damage dealt per game", True), ("damage_taken", "Damage taken per game", False),
           ("mulligans", "Mulligans per game", False), ("spells_per_turn", "Spells per turn", True),
           ("survived", "Games survived to the end", True)]


def _facts(rows, S, W):
    ft = Table([[Paragraph(t(a), S["cell"]), Paragraph(f"<b>{t(b)}</b>", S["cellr"])] for a, b in rows],
               colWidths=[W * 0.62, W * 0.38])
    ft.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL), ("LINEBELOW", (0, 0), (-1, -2), 0.5, LINE),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                            ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]))
    return ft


def _median(m):
    return f"turn {m}" if m else "after turn 10"


def _combo_section(CD, rep, S, W):
    gf = CD["goldfish"]
    out = [Paragraph("Combos and consistency", S["h2"]),
           Paragraph(t(f"Forge’s AI plays combos poorly, so this section measures your deck by goldfishing: "
                       f"{gf['games']:,} solo games in which the deck plays towards its combos on purpose "
                       "(ramp first, tutors fetch missing pieces). No opponents or interaction, so treat the "
                       "numbers as best-case speed."), S["small"]), Spacer(1, 5)]
    rows = [("Keepable 7-card opening hand", f"{gf['keep7']}%"),
            ("Non-land play on turn 1 / turn 2", f"{gf['t1_play']}% / {gf['t2_play']}%"),
            ("Commander cast on curve", f"{gf['cmd_on_curve']}%"),
            ("Mana screw (missed land drop by turn 3)", f"{gf['screw']}%"),
            ("Flood (8+ lands in first 13 cards)", f"{gf['flood']}%"),
            ("Average mana on turn 4 / turn 6", f"{gf['avg_mana_t4']} / {gf['avg_mana_t6']}")]
    if CD.get("available"):
        rows.append(("Combos in your deck", f"{CD.get('n_included', 0)} ({CD.get('n_wins', 0)} game-winning)"))
    if gf.get("combo_any"):
        ca = gf["combo_any"]
        rows.append(("Any combo assembled by turn 4 / 6 / 8", f"{ca['t4']}% / {ca['t6']}% / {ca['t8']}%"))
        rows.append(("Typical combo turn (median)", _median(ca["median"])))
    out.append(_facts(rows, S, W))
    if not CD.get("available"):
        out += [Spacer(1, 3), Paragraph(t(CD.get("error") or "Combo database unavailable."), S["small"])]

    if CD.get("included"):
        out.append(Paragraph("Your combos", S["h3"]))
        trs = [[Paragraph(h, S["th"]) for h in ("Combo", "Result", "Bracket", "By T6", "By T8", "Typical")]]
        for c in CD["included"][:10]:
            sp = c.get("speed") or {}
            trs.append([Paragraph(f'<link href="{escape(c["url"])}" color="#2F6FDE">{t(" + ".join(c["pieces"]))}</link>', S["cell"]),
                        Paragraph(t(", ".join(c["produces"][:2])), S["cell"]),
                        Paragraph(t(c.get("bracket_label") or "–"), S["cell"]),
                        Paragraph(f"{sp['t6']}%" if sp else "–", S["cellr"]),
                        Paragraph(f"{sp['t8']}%" if sp else "–", S["cellr"]),
                        Paragraph(t(_median(sp.get("median")) if sp else "–"), S["cellr"])])
        out.append(_table(trs, [W * 0.36, W * 0.22, W * 0.1, W * 0.09, W * 0.09, W * 0.14]))
        fx = CD.get("forge_check")
        if fx:
            out += [Spacer(1, 3), Paragraph(t(
                f"In the Forge games, your deck cast every piece of a winning combo in {fx['assembled']} of "
                f"{fx['games']} games and won {fx['won']} of those."), S["small"])]
    if CD.get("over_bracket"):
        out.append(Paragraph("Combos above your bracket", S["h3"]))
        out += [Paragraph(t(f"{' + '.join(c['pieces'])} – {c['bracket_label']} (bracket {c['bracket']})"),
                          S["bullet"], bulletText="•") for c in CD["over_bracket"]]
    if CD.get("almost"):
        out.append(Paragraph("One card away from a combo", S["h3"]))
        trs = [[Paragraph(h, S["th"]) for h in ("Add", "Completes", "Result")]]
        for a in CD["almost"][:6]:
            trs.append([Paragraph(f"<b>{t(a['missing'])}</b>", S["cell"]),
                        Paragraph(f'<link href="{escape(a["url"])}" color="#2F6FDE">{t(" + ".join(a["pieces"]))}</link>', S["cell"]),
                        Paragraph(t(", ".join(a["produces"][:2])), S["cell"])])
        out.append(_table(trs, [W * 0.25, W * 0.5, W * 0.25]))
        out.append(Paragraph(t(f"Only combos in your colours and allowed in bracket {rep['bracket']} are listed."), S["small"]))

    F, I = CD.get("field") or {}, CD.get("interaction") or {}
    if F.get("opponents"):
        out.append(Paragraph("Interaction in the field", S["h3"]))
        out.append(_facts([
            ("Counterspells per opponent deck (average)", f"{F['avg_counters']}"),
            ("Instant-speed removal per opponent deck (average)", f"{F['avg_instant_removal']}"),
            ("Chance one of 3 opponents has drawn a counterspell by turn 6", f"{F['pod_counter_by_t6']}%"),
            ("Your counterspells / instant-speed removal", f"{I.get('counters', 0)} / {I.get('instant_removal', 0)}"),
        ], S, W))
    out.append(Paragraph("Combo data from Commander Spellbook (commanderspellbook.com).", S["small"]))
    return out


def build_pdf(rep, path):
    S = _styles()
    R, A = rep["results"], rep["analysis"]
    me = next(s for s in R["standings"] if s["id"] == "D01")
    n = len(R["standings"])
    deck = rep["deck"]
    title = deck["name"] if deck.get("name") and deck["name"] != "Your deck" else " & ".join(deck["commanders"])
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=16 * mm, title=f"{_clean(title)} – test report",
                            author=APP_NAME)
    W = doc.width
    story = []

    # header
    story.append(Paragraph(t(f"{APP_NAME} · test tournament report"), S["kicker"]))
    story.append(Paragraph(t(title), S["title"]))
    meta = [f"Commander: {' & '.join(deck['commanders'])}" if title != " & ".join(deck["commanders"]) else None,
            f"Bracket {rep['bracket']}", f"{n} decks", f"{R['rounds']} rounds",
            "your pods only" if R["fast_mode"] else "full Swiss tournament", rep["created"]]
    if rep.get("demo"):
        meta.append("DEMO DATA")
    story.append(Paragraph(t("  |  ".join(m for m in meta if m)), S["kicker"]))
    story.append(Spacer(1, 4))
    story.append(Table([[""]], colWidths=[W], rowHeights=[2.5], style=[("BACKGROUND", (0, 0), (-1, -1), BLUE)]))
    story.append(Spacer(1, 10))

    # hero
    places = me["places"]
    cells, widths = [], []
    if not R["fast_mode"]:
        cells.append([Paragraph(f'{ordinal(me["rank"])} <font size="11" color="#5B6478">of {n}</font>', S["big"]),
                      Paragraph(t(f"Final standing · {me['points']:g} points"), S["small"])])
        widths.append(W * 0.28)
    cells.append([Paragraph(f'{me["avg_place"]} <font size="11" color="#5B6478">avg</font>', S["big"]),
                  Paragraph(t(f"Pod finish · {me['wins']} win{'s' if me['wins'] != 1 else ''} in {me['games']} games"),
                            S["small"])])
    widths.append(W * 0.28)
    cells.append([Badges(places, size=17, gap=4), Spacer(1, 6),
                  Paragraph(t(f"Pod finishes, rounds 1–{len(places)}"), S["small"])])
    widths.append(W - sum(widths))
    story.append(Table([cells], colWidths=widths, style=[
        ("BACKGROUND", (0, 0), (-1, -1), PANEL), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10), ("ROUNDEDCORNERS", [6, 6, 6, 6])]))

    # rounds
    story.append(Paragraph("Rounds", S["h2"]))
    rows = [[Paragraph(h, S["th"]) for h in ("Round", "Place", "Opponents", "Result")]]
    for g in sorted([g for g in R["games"] if "D01" in g["players"]], key=lambda g: g["round"]):
        p = g["players"]["D01"]
        opps = ", ".join(R["decks"][s]["name"] for s in g["seats"] if s != "D01")
        if p["won"]:
            res = "Won"
        elif g["draw"] and not p["eliminated"]:
            res = "Time limit"
        else:
            reason = p.get("loss_reason", "")
            res = ("Commander damage" if "21 damage" in reason else "Poison" if "poison" in reason
                   else "Decked" if "library" in reason else "Alt-win / combo" if "spell" in reason
                   else "Knocked out")
        rows.append([Paragraph(str(g["round"]), S["cellc"]),
                     Table([[Badges([p["place"]]), Paragraph(ordinal(p["place"]), S["cell"])]],
                           colWidths=[15, 30], style=[("LEFTPADDING", (0, 0), (-1, -1), 0),
                                                      ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]),
                     Paragraph(t(opps), S["cell"]), Paragraph(t(res), S["cell"])])
    story.append(_table(rows, [W * 0.09, W * 0.13, W * 0.58, W * 0.20]))

    # weak points
    story.append(Paragraph("Weak points", S["h2"]))
    if A["weak_points"]:
        for w in A["weak_points"]:
            box = Table([[Paragraph(f"<b>{t(w['title'])}</b><br/>{t(w['detail'])}", S["body"])]], colWidths=[W],
                        style=[("BACKGROUND", (0, 0), (-1, -1), BAD_BG), ("LINEBEFORE", (0, 0), (0, -1), 3.5, BAD),
                               ("LEFTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 5),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 6)])
            story += [box, Spacer(1, 4)]
    else:
        story.append(Paragraph("Nothing stood out as clearly weak.", S["body"]))
    if A["strengths"]:
        story.append(Paragraph("Strengths", S["h2"]))
        story += [Paragraph(t(s), S["bullet"], bulletText="•") for s in A["strengths"]]

    story.append(Paragraph("How to improve", S["h2"]))
    sugg = A["suggestions"] or ["Run more rounds for a clearer picture."]
    story += [Paragraph(t(s), S["bullet"], bulletText="•") for s in sugg]

    # cut / add columns
    def col(title, note, items):
        rows = [[Paragraph(f"<b>{t(title)}</b>", S["h3"]), ""], [Paragraph(t(note), S["small"]), ""]]
        rows += [[Paragraph(t(a), S["cell"]), Paragraph(t(b), S["cellr"])] for a, b in items]
        tb = Table(rows, colWidths=[W * 0.48 - 30, 30])
        tb.setStyle(TableStyle([("SPAN", (0, 0), (1, 0)), ("SPAN", (0, 1), (1, 1)),
                                ("LINEBELOW", (0, 2), (-1, -1), 0.4, LINE),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
        return tb
    cuts = [(c["card"], f"MV {c['cmc']:g}" if c.get("cmc") is not None else "") for c in A["cut_candidates"]]
    adds = [(c["card"] + (" ★" if c.get("fits_need") else ""), str(c["in_decks"])) for c in A["add_candidates"]]
    if cuts or adds:
        story.append(Spacer(1, 6))
        story.append(Table([[col("Cards to reconsider", "Never cast during testing", cuts or [("–", "")]),
                             col("Popular in similar decks", "Not in your deck · decks running it · ★ fits a weak point",
                                 adds or [("–", "")])]],
                           colWidths=[W / 2, W / 2],
                           style=[("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))

    # combos and consistency (goldfish + Commander Spellbook)
    CD = rep.get("combos")
    if CD and CD.get("goldfish"):
        story += _combo_section(CD, rep, S, W)

    if rep.get("ai_text"):
        story.append(Paragraph("Coaching notes from Claude", S["h2"]))
        story += _md_flowables(rep["ai_text"], S, W)

    # you vs field
    rows = [[Paragraph(h, S["th"]) for h in ("Measure", "You", "Other decks")]]
    for k, label, higher in METRICS:
        m = A["metrics"].get(k) or {}
        y, f = m.get("you"), m.get("field")
        if y is None:
            continue
        color = None
        if f is not None and abs(y - f) > 0.05 * max(1, abs(f)):
            color = GOOD if (y > f) == higher else BAD
        if k == "survived":
            ys, fs = f"{round(y * 100)}%", "–" if f is None else f"{round(f * 100)}%"
        else:
            ys, fs = f"{y:g}", "–" if f is None else f"{f:g}"
        ystyle = ParagraphStyle("y", parent=S["cellr"], textColor=color or INK)
        rows.append([Paragraph(label, S["cell"]), Paragraph(ys, ystyle), Paragraph(fs, S["cellr"])])
    story.append(KeepTogether([Paragraph("You vs. the field", S["h2"]), _table(rows, [W * 0.6, W * 0.2, W * 0.2])]))
    if A.get("eliminated_by"):
        story.append(Spacer(1, 3))
        story.append(Paragraph(t("Knocked out most often by: " +
                                 ", ".join(f"{a} ({b}×)" for a, b in A["eliminated_by"])), S["small"]))

    # standings
    if not R["fast_mode"]:
        rows = [[Paragraph(h, S["th"]) for h in ("#", "Deck", "Points", "Pod finishes")]]
        hl = []
        for i, s in enumerate(R["standings"], 1):
            mine = s["id"] == "D01"
            if mine:
                hl.append(i)
            st = S["cellb"] if mine else S["cell"]
            rows.append([Paragraph(str(s["rank"]), S["cellc"]),
                         Paragraph(t(s["name"] + (" (you)" if mine else "")), st),
                         Paragraph(f"{s['points']:g}", S["cellr"]), Badges(s["places"])])
        story.append(KeepTogether([Paragraph("Standings", S["h2"]),
                                   _table(rows, [W * 0.07, W * 0.55, W * 0.1, W * 0.28], highlight_rows=hl)]))
        story.append(Spacer(1, 3))
        story.append(Paragraph("Points per game: 1st 4, 2nd 2, 3rd 1, 4th 0. "
                               "Players still alive at the time limit get 1.", S["small"]))

    # opponents
    rows = [[Paragraph(h, S["th"]) for h in ("Deck", "Commander(s)", "Colours", "Bracket", "Source")]]
    for k, d in R["decks"].items():
        if k == "D01":
            continue
        link = f'<link href="{escape(d["url"])}" color="#2F6FDE">{t(d["name"])}</link>' if d.get("url") else t(d["name"])
        rows.append([Paragraph(link, S["cell"]), Paragraph(t(" & ".join(d["commanders"])), S["cell"]),
                     Paragraph(t(d.get("identity", "")), S["cellc"]), Paragraph(t(d.get("bracket") or "?"), S["cellc"]),
                     Paragraph(t(d.get("source", "")), S["cell"])])
    story.append(KeepTogether([Paragraph("Opponents", S["h2"]),
                               _table(rows, [W * 0.33, W * 0.33, W * 0.11, W * 0.1, W * 0.13])]))

    # summary: opening hands and early plays (tested deck only)
    E = A.get("early_game")
    if E and E["n"]:
        story.append(Paragraph("Summary: opening hands and early plays", S["h2"]))
        pct = lambda a, b: f" ({round(100 * a / b)}%)" if b else ""
        facts = [
            ("Non-land play on your turn 1", f"{E['t1_play']} of {E['t1_games']} games{pct(E['t1_play'], E['t1_games'])}"),
            ("Non-land play on your turn 2", f"{E['t2_play']} of {E['t2_games']} games{pct(E['t2_play'], E['t2_games'])}"),
            ("Non-land play on both turns", f"{E['both']} of {E['n']} games{pct(E['both'], E['n'])}"),
            ("Average kept hand", f"{E['avg_kept']} cards" + (f", {E['avg_lands_in_hand']} lands"
                                                            if E["avg_lands_in_hand"] is not None else "")),
        ]
        ft = Table([[Paragraph(t(a), S["cell"]), Paragraph(f"<b>{t(b)}</b>", S["cellr"])] for a, b in facts],
                   colWidths=[W * 0.6, W * 0.4])
        ft.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL), ("LINEBELOW", (0, 0), (-1, -2), 0.5, LINE),
                                ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        story += [ft, Spacer(1, 8)]

        def play_cell(cards):
            if cards is None:
                return Paragraph("Didn’t get this turn", S["small"])
            if not cards:
                return Paragraph(f'<font color="#B4372F"><b>No</b></font> – land only or nothing', S["cell"])
            return Paragraph(f'<font color="#2E7D4F"><b>Yes</b></font> – {t(", ".join(cards))}', S["cell"])

        rows = [[Paragraph(h, S["th"]) for h in ("Round", "Place", "Kept opening hand", "Turn 1", "Turn 2")]]
        for r in E["games"]:
            if r["hand"]:
                mull = r["mulligans"]
                extra = f"{r['kept']} cards, {r['lands_in_hand']} lands" + (
                    f", {mull} mulligan{'s' if mull != 1 else ''}" if mull else "")
                hand = Paragraph(f"{t(r['hand_text'])}<br/><font size=7.5 color='#5B6478'>{t(extra)}</font>", S["cell"])
            else:
                hand = Paragraph(t(f"Not recorded · kept {r['kept'] or '?'} cards"), S["small"])
            rows.append([Paragraph(str(r["round"]), S["cellc"]), Badges([r["place"]]), hand,
                         play_cell(r["t1"]), play_cell(r["t2"])])
        story.append(_table(rows, [W * 0.08, W * 0.08, W * 0.48, W * 0.18, W * 0.18]))
        if E["hands_recorded"] < E["n"]:
            story.append(Spacer(1, 3))
            story.append(Paragraph("Opening hands need Java's compiler (a JDK) and a Forge version the hand "
                                   "recorder works with; see the README.", S["small"]))
        story.append(Paragraph("Only your deck is shown. “Turn 1” and “Turn 2” are your own first two turns; "
                               "a play is any spell cast, lands don’t count.", S["small"]))

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Forge’s AI is a decent but imperfect pilot: look for patterns across rounds rather than single games. "
        "Unofficial fan-made tool, not affiliated with Wizards of the Coast, Forge, Commander Spellbook, Archidekt, "
        "Moxfield or Scryfall.",
        S["small"]))

    def footer(canv, d):
        canv.saveState()
        canv.setFont(_fonts()[0], 7.5)
        canv.setFillColor(MUTED)
        canv.drawCentredString(A4[0] / 2, 9 * mm, f"{_clean(title)}  ·  page {d.page}")
        canv.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path
