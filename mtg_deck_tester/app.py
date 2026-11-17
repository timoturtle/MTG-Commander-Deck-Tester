"""Local web app.  Run:  python -m mtg_deck_tester  [--demo] [--port 8765] [--no-browser]"""
import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys
import threading
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import (APP_NAME, __version__, analysis, archidekt, combos, demo, forge, moxfield, opponents, report_md,
               spellbook, tournament)
from .decklist import parse_decklist
from .scryfall import CardDB

DEMO = os.environ.get("MTG_DEMO") == "1"
HOME = os.path.expanduser(os.environ.get("MTG_HOME", os.path.join("~", APP_NAME)))
CACHE = os.path.join(HOME, "cache")
RESULTS = os.path.join(HOME, "results")
SETTINGS_FILE = os.path.join(HOME, "settings.json")
STATIC = os.path.join(os.path.dirname(__file__), "static")
for _d in (HOME, CACHE, RESULTS):
    os.makedirs(_d, exist_ok=True)

DEFAULT_SETTINGS = {"forge_folder": "", "api_key": "", "model": "claude-sonnet-5-5", "workers": 2,
                    "clock": 600, "moxfield_user_agent": ""}
FORGE_GUESSES = ["~/Forge", "~/forge", "~/Applications/Forge", "/Applications/Forge", "~/Downloads/forge*",
                 "~/Downloads/Forge*", "C:/Forge", "C:/Games/Forge", "~/Desktop/Forge*",
                 os.path.join(os.environ.get("ProgramFiles", "C:/Program Files"), "Forge")]


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                s.update(json.load(f))
        except Exception:
            pass
    if not s["forge_folder"]:
        for guess in FORGE_GUESSES:
            for path in glob.glob(os.path.expanduser(guess)):
                if forge.find_forge_jar(path):
                    s["forge_folder"] = path
                    return s
    return s


def save_settings(s):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1)
    try:
        os.chmod(SETTINGS_FILE, 0o600)  # holds API keys
    except Exception:
        pass


CARD_DB = CardDB(os.path.join(CACHE, "scryfall.json"))


class Job:
    def __init__(self):
        self.state = "idle"
        self.done = 0
        self.total = 0
        self.log = []
        self.error = ""
        self.report_id = None
        self.cancel = threading.Event()
        self.lock = threading.Lock()

    def say(self, msg):
        with self.lock:
            self.log.append(f"{datetime.datetime.now():%H:%M:%S}  {msg}")
            self.log = self.log[-400:]

    def snapshot(self):
        with self.lock:
            return {"state": self.state, "done": self.done, "total": self.total,
                    "log": self.log[-150:], "error": self.error, "report_id": self.report_id, "demo": DEMO}


JOB = Job()


def write_reports(rep, workdir, log=print):
    with open(os.path.join(workdir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f)
    with open(os.path.join(workdir, "report.md"), "w", encoding="utf-8") as f:
        f.write(report_md.to_markdown(rep))
    try:
        from . import report_pdf
        report_pdf.build_pdf(rep, os.path.join(workdir, "report.pdf"))
    except ImportError:
        log("PDF skipped: the 'reportlab' package is missing. Start the app with the start script, "
            "or run: pip install -r requirements.txt")
    except Exception as e:
        log(f"PDF could not be created: {e}")
        traceback.print_exc()


def run_job(req):
    job = JOB
    try:
        s = load_settings()
        job.say("Reading your decklist...")
        deck, warns = parse_decklist(req["text"], req.get("commander", ""), req.get("deck_name", ""))
        for w in warns:
            job.say("Note: " + w)
        if not deck.commanders:
            raise RuntimeError(warns[0])
        if not DEMO:
            job.say("Looking up your cards on Scryfall...")
            missing = CARD_DB.resolve(deck.all_names())
            if missing:
                job.say("Not recognised (Forge may skip these): " + ", ".join(missing[:15]))
            moved = opponents.clean_commanders(deck, CARD_DB)
            if moved:
                job.say(f"Note: {', '.join(moved)} can't be a commander; moved it into the deck.")
        prof = analysis.deck_profile(deck, CARD_DB)
        est, why = analysis.estimate_bracket(prof)
        bracket = int(req.get("bracket") or 0) or est
        job.say(f"Bracket {bracket}" + ("" if req.get("bracket") else f" (estimated: {why})"))

        need = int(req.get("field_size", 12)) - 1
        if DEMO:
            opps = demo.demo_opponents(need)
            job.say(f"Demo mode: using {len(opps)} built-in opponents.")
        else:
            arch = archidekt.Archidekt(CACHE, log=job.say)
            mox = moxfield.Moxfield(s.get("moxfield_user_agent", ""), CACHE, log=job.say)
            manual = []
            for link in re.split(r"[\s,]+", req.get("opponent_links", "") or ""):
                if not link or len(manual) >= need:
                    continue
                try:
                    if "moxfield" in link:
                        d = mox.fetch(moxfield.deck_id_from_url(link))
                    else:
                        did = archidekt.deck_id_from_url(link)
                        d = arch.fetch(did) if did else None
                except Exception as e:
                    job.say(f"  could not load {link}: {e}")
                    continue
                if d:
                    CARD_DB.resolve(d.commanders)
                    opponents.clean_commanders(d, CARD_DB)
                    manual.append(d)
                    job.say(f"  + {d.name} (your pick)")
            sources = [arch] + ([mox] if mox.enabled else [])
            if not mox.enabled:
                job.say("Moxfield is off (no Moxfield User-Agent in Settings); using Archidekt.")
            opps = opponents.pick(sources, deck, prof["identity"], bracket, need, CARD_DB, job.say, manual)
        if job.cancel.is_set():
            raise tournament.Cancelled()
        if len(opps) < 3:
            raise RuntimeError("Could not find at least 3 opponent decks. Paste some Archidekt or Moxfield "
                               "deck links into 'Specific opponents' and try again.")
        usable = ((len(opps) + 1) // 4) * 4 - 1
        if usable < need:
            job.say(f"Found {len(opps)} opponents; running with a field of {max(4, usable + 1)}.")
        opps = opps[:max(3, usable)]
        if not DEMO:
            job.say("Preparing opponent decks for Forge...")
            CARD_DB.resolve({n for o in opps for n in o.all_names()})
            idents = sorted(opponents.identity_str(opponents._identity(o, CARD_DB)) for o in opps)
            job.say("Colour identities in the field: " + ", ".join(idents))

        # combos + goldfish (before the games, so you see results early in the log)
        sb = demo.DemoSpellbook() if DEMO else spellbook.Spellbook(CACHE, log=job.say)
        try:
            combo_data = combos.analyze(deck, opps, CARD_DB, bracket, sb, log=job.say)
            gf = combo_data["goldfish"]
            job.say(f"Goldfish: keepable 7-card hand {gf['keep7']}%, commander on curve {gf['cmd_on_curve']}%"
                    + (f", combo by turn 8 in {gf['combo_any']['t8']}% of games" if gf.get("combo_any") else ""))
        except Exception as e:
            traceback.print_exc()
            combo_data = None
            job.say(f"Combo analysis skipped: {e}")
        if job.cancel.is_set():
            raise tournament.Cancelled()

        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        slug = re.sub(r"[^A-Za-z0-9]+", "-", deck.commanders[0])[:30].strip("-")
        rid = f"{stamp}_{slug}"
        workdir = os.path.join(RESULTS, rid)
        os.makedirs(workdir, exist_ok=True)

        if not DEMO:
            ok, msgs = forge.check_setup(s["forge_folder"])
            if not ok:
                raise RuntimeError(" ".join(msgs))

        def progress(done, total, msg):
            job.done, job.total = done, total
            job.say(msg)

        cfg = {"rounds": int(req.get("rounds", 5)), "fast": bool(req.get("fast")),
               "workers": int(s.get("workers", 2)), "clock": int(s.get("clock", 600)),
               "strong_ai": bool(req.get("strong_ai")), "forge_folder": s["forge_folder"], "demo": DEMO,
               "cache_dir": CACHE}
        job.say(f"Starting tournament: {len(opps) + 1} decks, {cfg['rounds']} rounds. "
                "Each Forge game takes a few minutes.")
        res = tournament.run_tournament(deck, opps, cfg, CARD_DB, workdir, progress, job.cancel)
        if not res["games"]:
            raise RuntimeError("No games finished. " + (res["errors"][0] if res["errors"] else ""))
        for e in res["errors"]:
            job.say("Warning: " + e[:300])

        job.say("Analysing results...")
        ana = analysis.weak_points_and_suggestions(res, deck, prof, CARD_DB, opps, bracket)
        if combo_data:
            combo_data["forge_check"] = combos.forge_crosscheck(combo_data, res, deck, CARD_DB)
            cw, cs = combos.weak_points(combo_data, bracket)
            ana["weak_points"] += [{"title": t, "detail": d} for t, d in cw]
            ana["suggestions"] += [x for x in cs if x not in ana["suggestions"]]
        rep = {"id": rid, "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
               "app_version": __version__, "deck": deck.to_dict(), "profile": prof, "bracket": bracket,
               "results": res, "analysis": ana, "combos": combo_data, "ai_text": "", "ai_error": "", "demo": DEMO}
        if req.get("use_ai"):
            if not s.get("api_key"):
                rep["ai_error"] = "No Claude API key saved in Settings."
            else:
                job.say("Asking Claude for coaching notes...")
                try:
                    rep["ai_text"] = analysis.ai_analysis(s["api_key"], s.get("model") or DEFAULT_SETTINGS["model"],
                                                          deck, prof, ana, res, bracket, combo_data)
                except Exception as e:
                    rep["ai_error"] = str(e)[:400]
                    job.say("AI analysis failed: " + rep["ai_error"])
        job.say("Writing the PDF report...")
        write_reports(rep, workdir, job.say)
        job.report_id = rid
        job.state = "done"
        job.say(f"Done. Report saved in {workdir}")
    except tournament.Cancelled:
        job.state = "cancelled"
        job.say("Stopped.")
    except Exception as e:
        job.state = "error"
        job.error = str(e)
        job.say("Error: " + str(e))
        traceback.print_exc()


def list_reports():
    out = []
    for d in sorted(os.listdir(RESULTS), reverse=True):
        if os.path.exists(os.path.join(RESULTS, d, "report.json")):
            out.append(d)
    return out[:50]


def open_in_file_browser(path):
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif os.name == "nt":
        os.startfile(path)  # only exists on Windows
    else:
        subprocess.Popen(["xdg-open", path])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}

    def _report_dir(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        rid = os.path.basename((q.get("id") or [""])[0]) or (list_reports() or [""])[0]
        d = os.path.join(RESULTS, rid)
        return (rid, d) if rid and os.path.isdir(d) else (None, None)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            with open(os.path.join(STATIC, "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if path == "/api/settings":
            s = load_settings()
            s["api_key_set"] = bool(s.pop("api_key"))
            s["moxfield_set"] = bool(s.pop("moxfield_user_agent"))
            s.update(demo=DEMO, version=__version__)
            return self._send(200, s)
        if path == "/api/status":
            return self._send(200, JOB.snapshot())
        if path == "/api/reports":
            return self._send(200, list_reports())
        if path in ("/api/report", "/api/report.pdf", "/api/report.md"):
            rid, d = self._report_dir()
            name = {"/api/report": "report.json", "/api/report.pdf": "report.pdf", "/api/report.md": "report.md"}[path]
            p = os.path.join(d, name) if d else None
            if (path == "/api/report.pdf" and d and not os.path.exists(p)
                    and os.path.exists(os.path.join(d, "report.json"))):
                with open(os.path.join(d, "report.json"), encoding="utf-8") as f:
                    write_reports(json.load(f), d)  # older reports: build the PDF on demand
            if not p or not os.path.exists(p):
                return self._send(404, {"error": "No report yet."})
            with open(p, "rb") as f:
                data = f.read()
            ctype = {"report.json": "application/json", "report.pdf": "application/pdf",
                     "report.md": "text/markdown; charset=utf-8"}[name]
            extra = {} if name == "report.json" else {
                "Content-Disposition": f'attachment; filename="{rid}.{name.split(".")[1]}"'}
            return self._send(200, data, ctype, extra)
        self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            body = self._body()
        except Exception:
            return self._send(400, {"error": "bad request"})
        if path == "/api/settings":
            s = load_settings()
            for k in ("forge_folder", "model"):
                if k in body:
                    s[k] = str(body[k]).strip().strip("'\"")
            for k in ("workers", "clock"):
                if k in body:
                    s[k] = max(1, int(body[k]))
            for k in ("api_key", "moxfield_user_agent"):
                if body.get(k):
                    s[k] = body[k].strip()
                if body.get("clear_" + k):
                    s[k] = ""
            save_settings(s)
            return self._send(200, {"ok": True})
        if path == "/api/check":
            if DEMO:
                return self._send(200, {"ok": True, "messages": ["Demo mode: Forge is not needed."]})
            ok, msgs = forge.check_setup(body.get("forge_folder") or load_settings()["forge_folder"])
            return self._send(200, {"ok": ok, "messages": msgs})
        if path == "/api/parse":
            deck, warns = parse_decklist(body.get("text", ""), body.get("commander", ""))
            missing = []
            if not DEMO and deck.size:
                try:
                    missing = CARD_DB.resolve(deck.all_names())
                    moved = opponents.clean_commanders(deck, CARD_DB)
                    if moved:
                        warns.append(f"{', '.join(moved)} can't be a commander; it was counted in the deck instead.")
                except Exception as e:
                    warns.append(f"Scryfall lookup failed: {e}")
            prof = analysis.deck_profile(deck, CARD_DB)
            est, why = analysis.estimate_bracket(prof)
            return self._send(200, {"commanders": deck.commanders, "size": deck.size, "warnings": warns,
                                    "unknown": missing, "profile": prof, "bracket_estimate": est,
                                    "bracket_reason": why})
        if path == "/api/start":
            if JOB.state == "running":
                return self._send(409, {"error": "A test is already running."})
            JOB.__init__()
            JOB.state = "running"
            threading.Thread(target=run_job, args=(body,), daemon=True).start()
            return self._send(200, {"ok": True})
        if path == "/api/cancel":
            JOB.cancel.set()
            JOB.say("Stopping...")
            return self._send(200, {"ok": True})
        if path == "/api/open-folder":
            rid = os.path.basename(body.get("id", ""))
            d = os.path.join(RESULTS, rid) if rid else RESULTS
            try:
                open_in_file_browser(d if os.path.isdir(d) else RESULTS)
                return self._send(200, {"ok": True})
            except Exception as e:
                return self._send(500, {"error": str(e)})
        self._send(404, {"error": "not found"})


def main():
    global DEMO
    ap = argparse.ArgumentParser(prog="mtg_deck_tester", description=APP_NAME)
    ap.add_argument("--demo", action="store_true", help="fake games, no Java/Forge needed")
    ap.add_argument("--port", type=int, default=int(os.environ.get("MTG_PORT", "8765")))
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    DEMO = DEMO or args.demo
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError:
        print(f"Port {args.port} is in use - is {APP_NAME} already running? "
              f"Open http://127.0.0.1:{args.port} or start with --port 8766")
        return
    url = f"http://127.0.0.1:{args.port}"
    print(f"{APP_NAME} {__version__}{' (demo mode)' if DEMO else ''} is running at {url}")
    print("Keep this window open while you use the app. Press Ctrl+C to quit.")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBye!")


if __name__ == "__main__":
    main()
