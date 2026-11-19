"""PDF report in the app's design language (Apple Human Interface Guidelines inspired):
clear hierarchy, grouped rounded sections, system colours, generous spacing. Font: Inter (OFL)."""
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
from reportlab.platypus import (CondPageBreak, Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

from . import APP_NAME

# Apple system colours (light appearance); text variants darkened for contrast on paper
LABEL = colors.HexColor("#1D1D1F")
SECONDARY = colors.HexColor("#6E6E73")
TERTIARY = colors.HexColor("#AEAEB2")
SEPARATOR = colors.HexColor("#E5E5EA")
GROUPED = colors.HexColor("#F2F2F7")
BLUE = colors.HexColor("#007AFF")
GREEN = colors.HexColor("#248A3D")
RED = colors.HexColor("#D70015")
ORANGE = colors.HexColor("#C93400")
RED_TINT = colors.HexColor("#FDEDEE")
BLUE_TINT = colors.HexColor("#E8F2FF")
PLACE = {1: colors.HexColor("#E0A800"), 2: colors.HexColor("#8E8E93"),
         3: colors.HexColor("#B4693C"), 4: colors.HexColor("#48484A")}

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
_FONT = None


def _fonts():
    """Inter (bundled) or, if missing, a system font; Helvetica as last resort."""
    global _FONT
    if _FONT:
        return _FONT
    candidates = [(os.path.join(FONT_DIR, "Inter-Regular.ttf"), os.path.join(FONT_DIR, "Inter-SemiBold.ttf"),
                   os.path.join(FONT_DIR, "Inter-Bold.ttf")),
                  ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                   "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
                  (os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeui.ttf"),
                   os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "seguisb.ttf"),
                   os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeuib.ttf"))]
    for reg, semi, bold in candidates:
        if all(os.path.exists(p) for p in (reg, semi, bold)):
            try:
                pdfmetrics.registerFont(TTFont("UI", reg))
                pdfmetrics.registerFont(TTFont("UI-Semi", semi))
                pdfmetrics.registerFont(TTFont("UI-Bold", bold))
                pdfmetrics.registerFontFamily("UI", normal="UI", bold="UI-Semi", italic="UI", boldItalic="UI-Semi")
                _FONT = ("UI", "UI-Semi", "UI-Bold", set(pdfmetrics.getFont("UI").face.charToGlyph.keys()))
                return _FONT
            except Exception:
                continue
    _FONT = ("Helvetica", "Helvetica-Bold", "Helvetica-Bold", None)
    return _FONT


def _clean(s):
    s = str(s if s is not None else "")
    glyphs = _fonts()[3]
    if glyphs is None:
        return "".join(ch for ch in s if ord(ch) < 256).strip()
    return "".join(ch for ch in s if ord(ch) in glyphs or ch in "\n\t").strip()


def t(s):
    return escape(_clean(s))


def ordinal(n):
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


def eur(v):
    if v is None:
        return "–"
    return f"€{v:,.2f}" if v < 100 else f"€{v:,.0f}"


def med(m, cap=10):
    return f"turn {m}" if m else f"after turn {cap}"


class Badges(Flowable):
    def __init__(self, places, size=11, gap=3):
        super().__init__()
        self.places, self.size, self.gap = [int(p) for p in places], size, gap

    def wrap(self, *_):
        return max(1, len(self.places)) * (self.size + self.gap), self.size

    def draw(self):
        c, r = self.canv, self.size / 2
        for i, p in enumerate(self.places):
            x = i * (self.size + self.gap) + r
            c.setFillColor(PLACE.get(p, PLACE[4]))
            c.circle(x, r, r, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont(_fonts()[1], self.size * 0.6)
            c.drawCentredString(x, r - self.size * 0.21, str(p))


def _styles():
    reg, semi, bold, _ = _fonts()
    b = dict(fontName=reg, textColor=LABEL, fontSize=9.5, leading=13.5)
    S = {
        "body": ParagraphStyle("body", **b),
        "secondary": ParagraphStyle("sec", **dict(b, fontSize=8.5, leading=12, textColor=SECONDARY)),
        "footnote": ParagraphStyle("fn", **dict(b, fontSize=7.5, leading=10.5, textColor=SECONDARY)),
        "cell": ParagraphStyle("cell", **dict(b, fontSize=8.5, leading=11.5)),
        "cellsec": ParagraphStyle("cellsec", **dict(b, fontSize=8, leading=11, textColor=SECONDARY)),
        "cellb": ParagraphStyle("cellb", **dict(b, fontName=semi, fontSize=8.5, leading=11.5)),
        "cellr": ParagraphStyle("cellr", **dict(b, fontSize=8.5, leading=11.5, alignment=TA_RIGHT)),
        "cellc": ParagraphStyle("cellc", **dict(b, fontSize=8.5, leading=11.5, alignment=TA_CENTER)),
        "th": ParagraphStyle("th", **dict(b, fontName=semi, fontSize=8, leading=10.5, textColor=SECONDARY)),
        "thr": ParagraphStyle("thr", **dict(b, fontName=semi, fontSize=8, leading=10.5, textColor=SECONDARY,
                                            alignment=TA_RIGHT)),
        "kicker": ParagraphStyle("kicker", **dict(b, fontName=semi, fontSize=8, textColor=BLUE)),
        "title": ParagraphStyle("title", **dict(b, fontName=bold, fontSize=26, leading=31)),
        "subtitle": ParagraphStyle("subtitle", **dict(b, fontSize=10, leading=14, textColor=SECONDARY)),
        "h2": ParagraphStyle("h2", **dict(b, fontName=bold, fontSize=15, leading=19, spaceBefore=16, spaceAfter=3,
                                          keepWithNext=1)),
        "h2sub": ParagraphStyle("h2sub", **dict(b, fontSize=8.5, leading=12, textColor=SECONDARY, spaceAfter=6,
                                                keepWithNext=1)),
        "h3": ParagraphStyle("h3", **dict(b, fontName=semi, fontSize=10.5, leading=14, spaceBefore=10, spaceAfter=4,
                                          keepWithNext=1)),
        "tile_value": ParagraphStyle("tv", **dict(b, fontName=bold, fontSize=20, leading=23)),
        "tile_label": ParagraphStyle("tl", **dict(b, fontSize=7.5, leading=10, textColor=SECONDARY)),
        "bullet": ParagraphStyle("bullet", **dict(b, leftIndent=11, bulletIndent=0, spaceAfter=3)),
    }
    return S


def _card(rows_or_flowables, W, pad=8, bg=GROUPED):
    """A rounded 'grouped' container (like an inset grouped list)."""
    inner = rows_or_flowables if isinstance(rows_or_flowables, list) else [rows_or_flowables]
    tb = Table([[f] for f in inner], colWidths=[W])
    tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("ROUNDEDCORNERS", [8, 8, 8, 8]),
                            ("LEFTPADDING", (0, 0), (-1, -1), pad), ("RIGHTPADDING", (0, 0), (-1, -1), pad),
                            ("TOPPADDING", (0, 0), (0, 0), pad), ("BOTTOMPADDING", (0, -1), (-1, -1), pad),
                            ("TOPPADDING", (0, 1), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -2), 0)]))
    return tb


def _list(rows, widths, S, header=None, highlight=()):
    """Inset grouped list: rounded grey background, hairline separators, optional header row."""
    data = ([header] if header else []) + rows
    tb = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("BACKGROUND", (0, 0), (-1, -1), GROUPED), ("ROUNDEDCORNERS", [8, 8, 8, 8]),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
          ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5)]
    first = 1 if header else 0
    for r in range(first, len(data) - 1):
        st.append(("LINEBELOW", (0, r), (-1, r), 0.4, SEPARATOR))
    if header:
        st.append(("LINEBELOW", (0, 0), (-1, 0), 0.6, TERTIARY))
    for r in highlight:
        st.append(("BACKGROUND", (0, r + first), (-1, r + first), BLUE_TINT))
    tb.setStyle(TableStyle(st))
    return tb


def _facts(pairs, S, W):
    rows = [[Paragraph(t(a), S["cell"]), Paragraph(f"<b>{t(b)}</b>", S["cellr"])] for a, b in pairs]
    return _list(rows, [W * 0.64, W * 0.36], S)


def _tiles(tiles, S, W, gap=6):
    n = len(tiles)
    w = (W - gap * (n - 1)) / n
    cells = []
    for value, label, color in tiles:
        vs = ParagraphStyle("v", parent=S["tile_value"], textColor=color or LABEL)
        cells.append(_card([Paragraph(value, vs), Spacer(1, 2), Paragraph(t(label), S["tile_label"])], w, pad=9))
    row, widths = [], []
    for i, c in enumerate(cells):
        row.append(c)
        widths.append(w)
        if i < n - 1:
            row.append("")
            widths.append(gap)
    tb = Table([row], colWidths=widths)
    tb.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return tb


def _section(story, title, S, subtitle=None):
    story.append(CondPageBreak(60 * mm))
    story.append(Paragraph(t(title), S["h2"]))
    if subtitle:
        story.append(Paragraph(t(subtitle), S["h2sub"]))


def _md(text, S, W):
    out, table = [], []

    def inline(s):
        s = t(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        return re.sub(r"`(.+?)`", r"\1", s)

    def flush():
        if table:
            n = max(len(r) for r in table)
            rows = [[Paragraph(inline(c), S["cell"]) for c in r + [""] * (n - len(r))] for r in table[1:]]
            head = [Paragraph(inline(c), S["th"]) for c in table[0] + [""] * (n - len(table[0]))]
            out.append(_list(rows, [W / n] * n, S, header=head))
            out.append(Spacer(1, 5))
            table.clear()

    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|"):
            if not re.match(r"^\|[\s:|-]+\|$", s):
                table.append([c.strip() for c in s.strip("|").split("|")])
            continue
        flush()
        if not s:
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", s)
        if m:
            out.append(Paragraph(inline(m.group(2)), S["h3"]))
        elif re.match(r"^[-*]\s+", s):
            out.append(Paragraph(inline(re.sub(r"^[-*]\s+", "", s)), S["bullet"], bulletText="•"))
        elif re.match(r"^\d+[.)]\s+", s):
            out.append(Paragraph(inline(re.sub(r"^\d+[.)]\s+", "", s)), S["bullet"],
                                 bulletText=re.match(r"^(\d+)", s).group(1) + "."))
        else:
            out.append(Paragraph(inline(s), S["body"]))
    flush()
    return out


METRICS = [("place", "Average pod finish", False), ("lands_t4", "Lands by your turn 4", True),
           ("first_spell", "First spell (your turn)", False), ("commander_turn", "Commander cast (your turn)", False),
           ("damage_dealt", "Damage dealt per game", True), ("damage_taken", "Damage taken per game", False),
           ("mulligans", "Mulligans per game", False), ("spells_per_turn", "Spells per turn", True),
           ("survived", "Games survived to the end", True)]


def build_pdf(rep, path):
    S = _styles()
    R, A = rep["results"], rep["analysis"]
    me = next(s for s in R["standings"] if s["id"] == "D01")
    n = len(R["standings"])
    deck = rep["deck"]
    cmd = " & ".join(deck["commanders"])
    title = deck["name"] if deck.get("name") and deck["name"] != "Your deck" else cmd
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"{_clean(title)} – test report", author=APP_NAME)
    W = doc.width
    story = []
    names = {k: d["name"] for k, d in R["decks"].items()}
    names["D01"] = "You"

    # ---------------- header
    story.append(Paragraph(t(f"{APP_NAME} test report"), S["kicker"]))
    story.append(Spacer(1, 3))
    story.append(Paragraph(t(title), S["title"]))
    story.append(Spacer(1, 2))
    sub = [cmd if title != cmd else None, f"Bracket {rep['bracket']}", f"{n} decks", f"{R['rounds']} rounds",
           "your pods only" if R["fast_mode"] else "Swiss tournament", rep["created"]]
    if rep.get("demo"):
        sub.append("demo data")
    story.append(Paragraph(t("  ·  ".join(x for x in sub if x)), S["subtitle"]))
    story.append(Spacer(1, 12))

    gf = (rep.get("combos") or {}).get("goldfish") or {}
    win_any = gf.get("win_any") or {}
    tiles = []
    if not R["fast_mode"]:
        tiles.append((f'{ordinal(me["rank"])} <font size="11" color="#6E6E73">of {n}</font>',
                      f"Final standing · {me['points']:g} points", None))
    tiles.append((f'{me["avg_place"]} <font size="11" color="#6E6E73">avg</font>',
                  f"Pod finish · {me['wins']} win{'s' if me['wins'] != 1 else ''} in {me['games']}", None))
    if win_any:
        tiles.append((t(med(win_any.get("median"), 15).replace("turn ", "T").replace("after T15", "T15+")),
                      "Typical solo win (goldfish)", None))
    if rep.get("value") is not None:
        tiles.append((t(eur(rep["value"])), "Deck value (Cardmarket)", None))
    story.append(_tiles(tiles, S, W))
    story.append(Spacer(1, 8))
    story.append(Badges(me["places"], size=15, gap=4))
    story.append(Spacer(1, 2))
    story.append(Paragraph(t(f"Your place in each pod, rounds 1–{len(me['places'])}"), S["footnote"]))

    su = rep.get("settings_used") or {}
    if su:
        mull = su.get("mulligan")
        rule = (f"keep {mull['min_lands']}–{mull['max_lands']} lands"
                + (", needs a 2-mana play" if mull.get("need_cheap") else "")
                + f", max {mull.get('max_mulligans', 2)} mulligans") if mull else "Forge decides"
        story.append(Spacer(1, 8))
        story.append(Paragraph(t(f"AI personality: you {su.get('ai_profile_you')}, opponents {su.get('ai_profile_opp')}"
                                 f"  ·  Mulligans: {rule}"
                                 + ("  ·  Opponents matched to your deck value (±30%)" if rep.get("value_match") else "")),
                               S["footnote"]))

    # ---------------- rounds
    _section(story, "Rounds", S)
    rows = []
    for g in sorted([g for g in R["games"] if "D01" in g["players"]], key=lambda g: g["round"]):
        p = g["players"]["D01"]
        opps = ", ".join(R["decks"][s]["name"] for s in g["seats"] if s != "D01")
        reason = p.get("loss_reason", "")
        res = ("Won" if p["won"] else "Time limit / stalled" if g["draw"] and not p["eliminated"]
               else "Commander damage" if "21 damage" in reason else "Poison" if "poison" in reason
               else "Alt-win / combo" if "spell" in reason or "effect" in reason else "Knocked out")
        rows.append([Paragraph(str(g["round"]), S["cellc"]), Badges([p["place"]]), Paragraph(t(opps), S["cell"]),
                     Paragraph(t(res), S["cell"])])
    head = [Paragraph(h, S["th"]) for h in ("Round", "", "Opponents", "Result")]
    story.append(_list(rows, [W * 0.09, W * 0.07, W * 0.62, W * 0.22], S, header=head))

    # ---------------- weak points
    _section(story, "Weak points", S)
    if A["weak_points"]:
        for w in A["weak_points"]:
            story.append(_card([Paragraph(f"<b>{t(w['title'])}</b>", S["body"]),
                                Paragraph(t(w["detail"]), S["secondary"])], W, pad=8, bg=RED_TINT))
            story.append(Spacer(1, 4))
    else:
        story.append(Paragraph("Nothing stood out as clearly weak.", S["body"]))
    if A["strengths"]:
        story.append(Paragraph("Strengths", S["h3"]))
        story += [Paragraph(t(s), S["bullet"], bulletText="•") for s in A["strengths"]]

    # ---------------- upgrades for the budget
    U = rep.get("upgrades") or {}
    if U.get("swaps"):
        bud = U.get("budget")
        _section(story, "Recommended upgrades",
                 S, (f"Best impact for your budget of {eur(bud)}: {eur(U['spent'])} spent." if bud else
                     "Highest-impact swaps, with prices.") +
                 " Impact combines EDHREC popularity and synergy, your weak points and combos.")
        rows = []
        for sw in U["swaps"]:
            rows.append([Paragraph(f"<b>{t(sw['add'])}</b><br/><font size=7.5 color='#6E6E73'>{t(sw['why'])}</font>",
                                   S["cell"]),
                         Paragraph(t(eur(sw["price"])), S["cellr"]),
                         Paragraph(f"{t(sw['cut'])}<br/><font size=7.5 color='#6E6E73'>{t(sw['cut_why'])}</font>",
                                   S["cell"])])
        head = [Paragraph("Add", S["th"]), Paragraph("Price", S["thr"]), Paragraph("Cut", S["th"])]
        story.append(_list(rows, [W * 0.45, W * 0.13, W * 0.42], S, header=head))
        story.append(Spacer(1, 3))
        story.append(Paragraph("Prices: Cardmarket trend via Scryfall for one printing; your copies may cost less.",
                               S["footnote"]))

    _section(story, "How to improve", S)
    story += [Paragraph(t(s), S["bullet"], bulletText="•") for s in (A["suggestions"] or
                                                                     ["Run more rounds for a clearer picture."])]
    cuts = A.get("cut_candidates") or []
    adds = A.get("add_candidates") or []
    if cuts or adds:
        def col(title, note, items, w):
            rows = [[Paragraph(t(a), S["cell"]), Paragraph(t(b), S["cellr"])] for a, b in items] or \
                [[Paragraph("–", S["cell"]), ""]]
            return [Paragraph(t(title), S["h3"]), Paragraph(t(note), S["footnote"]), Spacer(1, 3),
                    _list(rows, [w * 0.7, w * 0.3], S)]
        w = (W - 10) / 2
        left = col("Cards to reconsider", "Never cast during testing",
                   [(c["card"], f"MV {c['cmc']:g}" if c.get("cmc") is not None else "") for c in cuts], w)
        right = col("Popular in the opponent decks", "Not in your deck · price · ★ fits a weak point",
                    [(c["card"] + (" ★" if c.get("fits_need") else ""), eur(c.get("price"))) for c in adds[:10]], w)
        tb = Table([[left, "", right]], colWidths=[w, 10, w])
        tb.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(tb)

    # ---------------- EDHREC
    E = rep.get("edhrec")
    if E:
        dk = f"{E['decks']:,} decks" if isinstance(E.get("decks"), int) else "decks"
        _section(story, "Compared with EDHREC", S,
                 f"How players build {cmd}, from {dk} on EDHREC."
                 + (f" Your non-land cards appear in {E['avg_inclusion_of_yours']}% of those decks on average."
                    if E.get("avg_inclusion_of_yours") is not None else ""))
        w = (W - 10) / 2
        miss = [[Paragraph(t(m["card"]), S["cell"]), Paragraph(f"{m['inclusion']:.0f}%", S["cellr"]),
                 Paragraph(t(eur(m.get("price"))), S["cellr"])] for m in E.get("missing", [])[:10]]
        unus = [[Paragraph(t(u["card"]), S["cell"]),
                 Paragraph("not listed" if u["inclusion"] is None else f"{u['inclusion']:.0f}%", S["cellr"])]
                for u in E.get("unusual", [])[:10]]
        left = [Paragraph("Popular cards you don't play", S["h3"]),
                _list(miss or [[Paragraph("–", S["cell"]), "", ""]], [w * 0.6, w * 0.18, w * 0.22], S,
                      header=[Paragraph("Card", S["th"]), Paragraph("Decks", S["thr"]), Paragraph("Price", S["thr"])])]
        right = [Paragraph("Your unusual picks", S["h3"]),
                 _list(unus or [[Paragraph("–", S["cell"]), ""]], [w * 0.7, w * 0.3], S,
                       header=[Paragraph("Card", S["th"]), Paragraph("Decks", S["thr"])])]
        tb = Table([[left, "", right]], colWidths=[w, 10, w])
        tb.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(tb)
        story.append(Spacer(1, 3))
        story.append(Paragraph("Unusual picks are your spice, or candidates to cut. Data: edhrec.com.", S["footnote"]))

    # ---------------- combos, consistency and win check
    CD = rep.get("combos")
    if CD and CD.get("goldfish"):
        story += _combo_section(CD, rep, S, W)

    if rep.get("ai_text"):
        _section(story, "Coaching notes from Claude", S)
        story += _md(rep["ai_text"], S, W)

    # ---------------- you vs field
    rows = []
    for k, label, higher in METRICS:
        m = A["metrics"].get(k) or {}
        y, f = m.get("you"), m.get("field")
        if y is None:
            continue
        col = LABEL
        if f is not None and abs(y - f) > 0.05 * max(1, abs(f)):
            col = GREEN if (y > f) == higher else RED
        ys, fs = (f"{round(y * 100)}%", "–" if f is None else f"{round(f * 100)}%") if k == "survived" else \
            (f"{y:g}", "–" if f is None else f"{f:g}")
        rows.append([Paragraph(label, S["cell"]),
                     Paragraph(f"<b>{ys}</b>", ParagraphStyle("y", parent=S["cellr"], textColor=col)),
                     Paragraph(fs, S["cellr"])])
    _section(story, "You vs. the field", S)
    story.append(_list(rows, [W * 0.6, W * 0.2, W * 0.2], S,
                       header=[Paragraph("Measure", S["th"]), Paragraph("You", S["thr"]), Paragraph("Others", S["thr"])]))
    if A.get("eliminated_by"):
        story.append(Spacer(1, 3))
        story.append(Paragraph(t("Knocked out most often by: " + ", ".join(f"{a} ({b}×)" for a, b in A["eliminated_by"])),
                               S["footnote"]))

    if not R["fast_mode"]:
        _section(story, "Standings", S)
        rows, hl = [], []
        for i, s in enumerate(R["standings"]):
            mine = s["id"] == "D01"
            if mine:
                hl.append(i)
            rows.append([Paragraph(str(s["rank"]), S["cellc"]),
                         Paragraph(t(s["name"] + (" (you)" if mine else "")), S["cellb"] if mine else S["cell"]),
                         Paragraph(f"{s['points']:g}", S["cellr"]), Badges(s["places"])])
        story.append(_list(rows, [W * 0.07, W * 0.55, W * 0.1, W * 0.28], S, highlight=hl,
                           header=[Paragraph("#", S["th"]), Paragraph("Deck", S["th"]), Paragraph("Points", S["thr"]),
                                   Paragraph("Pod finishes", S["th"])]))
        story.append(Spacer(1, 3))
        story.append(Paragraph("Points per game: 1st 4, 2nd 2, 3rd 1, 4th 0. Players alive when a game is stopped get 1.",
                               S["footnote"]))

    rows = []
    for k, d in R["decks"].items():
        if k == "D01":
            continue
        link = f'<link href="{escape(d["url"])}" color="#007AFF">{t(d["name"])}</link>' if d.get("url") else t(d["name"])
        rows.append([Paragraph(link, S["cell"]), Paragraph(t(" & ".join(d["commanders"])), S["cell"]),
                     Paragraph(t(d.get("identity", "")), S["cellc"]), Paragraph(t(eur(d.get("value"))), S["cellr"]),
                     Paragraph(t(d.get("source", "")), S["cellsec"])])
    _section(story, "Opponents", S)
    story.append(_list(rows, [W * 0.32, W * 0.32, W * 0.1, W * 0.12, W * 0.14], S,
                       header=[Paragraph(h, S["th"]) for h in ("Deck", "Commander", "Colours", "Value", "Source")]))

    # ---------------- opening hands (summary at the end, as requested by users)
    story += _early_section(A.get("early_game"), S, W)
    # ---------------- key moments (appendix)
    story += _moments_section(R, names, S, W)

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Forge’s AI is a decent but imperfect pilot: look for patterns across rounds rather than single games. "
        "Unofficial fan-made tool, not affiliated with Wizards of the Coast, Forge, Commander Spellbook, EDHREC, "
        "Archidekt, Moxfield or Scryfall.", S["footnote"]))

    def footer(canv, d):
        canv.saveState()
        canv.setFont(_fonts()[0], 7.5)
        canv.setFillColor(SECONDARY)
        canv.drawString(16 * mm, 9 * mm, _clean(title))
        canv.drawRightString(A4[0] - 16 * mm, 9 * mm, f"{d.page}")
        canv.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path


def _combo_section(CD, rep, S, W):
    gf = CD["goldfish"]
    out = []
    _section(out, "Combos and consistency", S,
             f"Goldfish estimate: {gf['games']:,} solo games that play towards the deck’s plan on purpose. "
             "No opponents, so this is best-case speed – but it shows what Forge’s AI misses.")
    rows = [("Keepable 7-card opening hand", f"{gf['keep7']}%"),
            ("Non-land play on turn 1 / turn 2", f"{gf['t1_play']}% / {gf['t2_play']}%"),
            ("Commander cast on curve", f"{gf['cmd_on_curve']}%"),
            ("Mana screw / flood", f"{gf['screw']}% / {gf['flood']}%"),
            ("Average mana on turn 4 / turn 6", f"{gf['avg_mana_t4']} / {gf['avg_mana_t6']}")]
    if CD.get("available"):
        rows.append(("Combos in your deck", f"{CD.get('n_included', 0)} ({CD.get('n_wins', 0)} game-winning)"))
    if gf.get("combo_any"):
        ca = gf["combo_any"]
        rows.append(("Any combo assembled by turn 4 / 6 / 8", f"{ca['t4']}% / {ca['t6']}% / {ca['t8']}%"))
    out.append(_facts(rows, S, W))
    if not CD.get("available"):
        out += [Spacer(1, 3), Paragraph(t(CD.get("error") or "Combo database unavailable."), S["footnote"])]

    win, wa = gf.get("win") or {}, gf.get("win_any") or {}
    if wa:
        out.append(Paragraph("Win check: how fast the deck wins alone", S["h3"]))
        src = win.get("sources") or {}
        src_txt = ", ".join(f"{k} {v}%" for k, v in sorted(src.items(), key=lambda x: -x[1])) or "–"
        pairs = [("Wins alone by turn 8 / 10 / 12", f"{wa['t8']}% / {wa['t10']}% / {wa['t12']}%"),
                 ("Typical winning turn", med(wa.get("median"), 15)),
                 ("Where the damage comes from", src_txt)]
        if win.get("alt_win_cards"):
            alt = win.get("altwin") or {}
            pairs.append(("“Win the game” cards castable by turn 8", f"{alt.get('t8', 0)}%  ({', '.join(win['alt_win_cards'][:3])})"))
        out.append(_facts(pairs, S, W))
        out.append(Spacer(1, 3))
        out.append(Paragraph("Three opponents at 40 life who never block or interact; includes combat, commander "
                             "damage, drain, poison, mill and game-winning combos. Tokens and pump effects aren’t "
                             "counted, so go-wide decks are faster than shown.", S["footnote"]))

    if CD.get("included"):
        out.append(Paragraph("Your combos", S["h3"]))
        rows = []
        for c in CD["included"][:10]:
            sp = c.get("speed") or {}
            rows.append([Paragraph(f'<link href="{escape(c["url"])}" color="#007AFF">{t(" + ".join(c["pieces"]))}</link>',
                                   S["cell"]),
                         Paragraph(t(", ".join(c["produces"][:2])), S["cellsec"]),
                         Paragraph(t(c.get("bracket_label") or "–"), S["cellsec"]),
                         Paragraph(f"{sp['t8']}%" if sp else "–", S["cellr"]),
                         Paragraph(t(med(sp.get("median")) if sp else "–"), S["cellr"])])
        out.append(_list(rows, [W * 0.38, W * 0.22, W * 0.11, W * 0.11, W * 0.18], S,
                         header=[Paragraph(h, S["th"]) for h in ("Combo", "Result", "Bracket")] +
                         [Paragraph("By turn 8", S["thr"]), Paragraph("Typical", S["thr"])]))
        fx = CD.get("forge_check")
        if fx:
            out += [Spacer(1, 3), Paragraph(t(f"In the Forge games, your deck cast every piece of a winning combo in "
                                              f"{fx['assembled']} of {fx['games']} games and won {fx['won']} of those."),
                                            S["footnote"])]
    if CD.get("over_bracket"):
        out.append(Paragraph("Combos above your bracket", S["h3"]))
        out += [Paragraph(t(f"{' + '.join(c['pieces'])} – {c['bracket_label']} (bracket {c['bracket']})"),
                          S["bullet"], bulletText="•") for c in CD["over_bracket"]]
    if CD.get("almost"):
        out.append(Paragraph("One card away from a combo", S["h3"]))
        rows = [[Paragraph(f"<b>{t(a['missing'])}</b>", S["cell"]), Paragraph(t(eur(a.get("price"))), S["cellr"]),
                 Paragraph(f'<link href="{escape(a["url"])}" color="#007AFF">{t(" + ".join(a["pieces"]))}</link>', S["cell"]),
                 Paragraph(t(", ".join(a["produces"][:2])), S["cellsec"])] for a in CD["almost"][:6]]
        out.append(_list(rows, [W * 0.24, W * 0.1, W * 0.42, W * 0.24], S,
                         header=[Paragraph("Add", S["th"]), Paragraph("Price", S["thr"]), Paragraph("Completes", S["th"]),
                                 Paragraph("Result", S["th"])]))
    F, I = CD.get("field") or {}, CD.get("interaction") or {}
    if F.get("opponents"):
        out.append(Paragraph("Interaction in the field", S["h3"]))
        out.append(_facts([("Counterspells per opponent deck (average)", f"{F['avg_counters']}"),
                           ("Instant-speed removal per opponent deck (average)", f"{F['avg_instant_removal']}"),
                           ("Chance one of 3 opponents has drawn a counterspell by turn 6", f"{F['pod_counter_by_t6']}%"),
                           ("Your counterspells / instant-speed removal",
                            f"{I.get('counters', 0)} / {I.get('instant_removal', 0)}")], S, W))
    out.append(Spacer(1, 3))
    out.append(Paragraph("Combo data: commanderspellbook.com.", S["footnote"]))
    return out


def _early_section(E, S, W):
    if not E or not E.get("n"):
        return []
    out = []
    _section(out, "Opening hands and early plays", S, "Your deck only. Turn 1 and 2 are your own first turns; "
                                                       "a play is any spell cast, lands don’t count.")
    pct = lambda a, b: f" ({round(100 * a / b)}%)" if b else ""
    out.append(_facts([
        ("Non-land play on your turn 1", f"{E['t1_play']} of {E['t1_games']} games{pct(E['t1_play'], E['t1_games'])}"),
        ("Non-land play on your turn 2", f"{E['t2_play']} of {E['t2_games']} games{pct(E['t2_play'], E['t2_games'])}"),
        ("Non-land play on both turns", f"{E['both']} of {E['n']} games{pct(E['both'], E['n'])}"),
        ("Average kept hand", f"{E['avg_kept']} cards" + (f", {E['avg_lands_in_hand']} lands"
                                                         if E.get("avg_lands_in_hand") is not None else ""))], S, W))
    out.append(Spacer(1, 6))

    def play(c):
        if c is None:
            return Paragraph("didn’t get this turn", S["cellsec"])
        if not c:
            return Paragraph('<font color="#D70015"><b>No</b></font>', S["cell"])
        return Paragraph(f'<font color="#248A3D"><b>Yes</b></font> · {t(", ".join(c))}', S["cell"])
    rows = []
    for r in E["games"]:
        if r["hand"]:
            extra = f"{r['kept']} cards, {r['lands_in_hand']} lands" + (
                f", {r['mulligans']} mulligan{'s' if r['mulligans'] != 1 else ''}" if r["mulligans"] else "")
            hand = Paragraph(f"{t(r['hand_text'])}<br/><font size=7.5 color='#6E6E73'>{t(extra)}</font>", S["cell"])
        else:
            hand = Paragraph(t(f"not recorded · kept {r['kept'] or '?'} cards"), S["cellsec"])
        rows.append([Paragraph(str(r["round"]), S["cellc"]), Badges([r["place"]]), hand, play(r["t1"]), play(r["t2"])])
    out.append(_list(rows, [W * 0.08, W * 0.07, W * 0.49, W * 0.18, W * 0.18], S,
                     header=[Paragraph(h, S["th"]) for h in ("Round", "", "Kept opening hand", "Turn 1", "Turn 2")]))
    return out


def _moments_section(R, names, S, W):
    games = sorted([g for g in R["games"] if "D01" in g["players"] and g.get("timeline")], key=lambda g: g["round"])
    if not games:
        return []
    out = []
    _section(out, "Key moments", S, "What your deck did in each game, round by round (one round = every player "
                                    "took a turn). Life totals at the end of the round.")

    def short(k):
        nm = names.get(k, k)
        return nm if len(nm) <= 16 else nm[:15] + "…"

    def fix(text):
        for k, nm in names.items():
            text = text.replace(k + " ", nm + " ")
        return text

    for g in games:
        p = g["players"]["D01"]
        opp = [s for s in g["seats"] if s != "D01"]
        block = [Paragraph(t(f"Round {g['round']}  ·  {ordinal(p['place'])} place"), S["h3"]),
                 Paragraph(t("Life column: you · " + " · ".join(names[s] for s in opp)), S["footnote"]),
                 Spacer(1, 3)]
        rows = []
        for T in g["timeline"][:18]:
            plays = [", ".join(T["cast"])] if T["cast"] else []
            life = T.get("life") or {}
            lt = f"<b>{life.get('D01', '–')}</b> · " + " · ".join(str(life.get(s, '–')) for s in opp)
            notes = [fix(e["text"]) for e in T.get("events", [])]
            if T.get("taken", 0) >= 8:
                notes.append(f"took {T['taken']} damage")
            if T.get("dealt", 0) >= 8:
                notes.append(f"dealt {T['dealt']} damage")
            if not T["cast"] and not notes and T["round"] > 2:
                continue  # only lands played: nothing to tell
            rows.append([Paragraph(str(T["round"]), S["cellc"]), Paragraph(t(" · ".join(plays) or "–"), S["cell"]),
                         Paragraph(lt, S["cell"]), Paragraph(t("; ".join(notes)), S["cellsec"])])
        if rows:
            block.append(_list(rows, [W * 0.08, W * 0.42, W * 0.17, W * 0.33], S,
                               header=[Paragraph(h, S["th"]) for h in ("#", "Your spells", "Life", "Notes")]))
        out += block
    return out
