"""Smoke tests: no network, no Java/Forge needed. Run with:  python -m unittest discover -s tests -v"""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mtg_deck_tester import forge, goldfish, scryfall  # noqa: E402
from mtg_deck_tester.decklist import Deck, parse_decklist  # noqa: E402


class CardDBApi(unittest.TestCase):
    def test_every_card_db_method_the_app_calls_exists(self):
        """Guards against a method being deleted while code still calls it (bug in 3.3.1)."""
        called = set()
        for path in glob.glob(os.path.join(ROOT, "mtg_deck_tester", "*.py")):
            with open(path, encoding="utf-8") as f:
                called |= set(re.findall(r"\b(?:CARD_DB|card_db)\.(\w+)\(", f.read()))
        self.assertTrue(called, "no calls found - pattern broken?")
        for name in sorted(called):
            self.assertTrue(callable(getattr(scryfall.CardDB, name, None)), f"CardDB.{name}() is missing")

    def test_resolve_cheapest_price_with_mocked_scryfall(self):
        db = scryfall.CardDB(os.path.join(tempfile.mkdtemp(), "cards.json"))

        def card(name, eur):
            return {"name": name, "layout": "normal", "cmc": 1, "type_line": "Artifact", "oracle_text": "",
                    "color_identity": [], "prices": {"eur": eur, "usd": None}, "legalities": {"commander": "legal"}}
        old_post, old_get = scryfall.post_json, scryfall.get_json
        try:
            scryfall.post_json = lambda url, payload, **k: {"data": [card(i["name"], "5.00") for i in payload["identifiers"]]}
            scryfall.get_json = lambda url, **k: {"data": [card("Sol Ring", "9.00"), card("Sol Ring", "1.25")], "has_more": False}
            self.assertEqual(db.resolve(["Sol Ring"]), [])
            self.assertEqual(db.price("Sol Ring"), 5.0)
            db.cheapest(["Sol Ring"], 1.0)
            self.assertEqual(db.price("Sol Ring"), 1.25)
            self.assertEqual(scryfall.deck_value(Deck("x", ["Sol Ring"], []), db), (1.25, 0))
        finally:
            scryfall.post_json, scryfall.get_json = old_post, old_get


class Parsing(unittest.TestCase):
    def test_archidekt_text(self):
        deck, _ = parse_decklist("1x Krenko, Mob Boss (rvr) 1 [Commander{top}]\n1x Sol Ring (cmm) 2 [Ramp]\n"
                                 "1x Junk (abc) 3 [Maybeboard{noDeck}]\n97x Mountain (abc) 4 [Land]")
        self.assertEqual(deck.commanders, ["Krenko, Mob Boss"])
        self.assertEqual(deck.size, 99)

    def test_rounds_continue_after_first_player_is_out(self):
        lines, t = ["Simulation mode"], 0
        for rnd in range(1, 6):
            for s in (3, 4, 1, 2):
                if s == 3 and rnd > 2:
                    continue
                t += 1
                lines.append(f"Turn: Turn {t} (Ai({s})-D0{s})")
                if s == 1:
                    lines.append(f"Add To Stack: Ai(1)-D01 cast Spell {rnd}")
                if s == 2:
                    lines.append("Damage: Bear (7) deals 2 combat damage to Ai(4)-D04.")
            if rnd == 2:
                lines.append("Life: Life: Ai(3)-D03 5 > 0")
        lines += ["Game Outcome: Ai(3)-D03 has lost because life total reached 0", "",
                  "Game Result: Game 1 ended in a Draw! Took 1 ms."]
        r = forge.parse_game("\n".join(lines), ["D01", "D02", "D03", "D04"], {}, {"D02": {"Bear"}}, focus="D01")
        self.assertEqual([T["cast"] for T in r.timeline], [[f"Spell {i}"] for i in range(1, 6)])
        self.assertEqual(r.players["D02"].damage_dealt, 10)  # opponents' damage is counted too


class Goldfish(unittest.TestCase):
    def test_runs(self):
        d = Deck("x", ["Cmd"], [(36, "Island"), (63, "Bear")])
        r = goldfish.Goldfish(d, None).run(200, seed=1)
        self.assertGreater(r["keep7"], 0)
        self.assertIn("card_drawn_by_t8", r)


class DemoEndToEnd(unittest.TestCase):
    def test_demo_run_produces_report_and_pdf(self):
        home = tempfile.mkdtemp()
        env = dict(os.environ, MTG_HOME=home)
        port = "8877"
        srv = subprocess.Popen([sys.executable, "-m", "mtg_deck_tester", "--demo", "--no-browser", "--port", port],
                               cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(50):
                try:
                    urllib.request.urlopen(base + "/api/status", timeout=2)
                    break
                except Exception:
                    time.sleep(0.2)
            text = "\n".join(["1x Krenko, Mob Boss [Commander]"] + [f"1x Goblin {i}" for i in range(60)] + ["39x Mountain"])
            body = json.dumps({"text": text, "rounds": 3, "field_size": 8, "focus": "Goblin 3"}).encode()
            urllib.request.urlopen(urllib.request.Request(base + "/api/start", data=body, method="POST",
                                                          headers={"Content-Type": "application/json"}), timeout=10)
            state = "running"
            for _ in range(150):
                state = json.load(urllib.request.urlopen(base + "/api/status", timeout=5))["state"]
                if state != "running":
                    break
                time.sleep(0.2)
            self.assertEqual(state, "done")
            rep = json.load(urllib.request.urlopen(base + "/api/report", timeout=10))
            self.assertEqual(rep.get("pdf_error"), "")
            pdf = urllib.request.urlopen(base + "/api/report.pdf?id=" + rep["id"], timeout=30).read()
            self.assertTrue(pdf.startswith(b"%PDF"))
        finally:
            srv.terminate()
            srv.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
