"""Run Forge's headless simulation mode and parse its game logs."""
from __future__ import annotations
import glob
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field

JAVA_ARGS = [
    "-Xmx4096m", "-Dio.netty.tryReflectionSetAccessible=true", "-Dfile.encoding=UTF-8",
    "-Dstdout.encoding=UTF-8", "-Dsun.stdout.encoding=UTF-8", "-Djava.awt.headless=true",
    "-Dapple.awt.UIElement=true",  # no Dock icon on macOS (ignored elsewhere)
]
ADD_OPENS = ("java.desktop/java.beans java.desktop/javax.swing.border java.desktop/javax.swing.event "
             "java.desktop/sun.swing java.desktop/java.awt.image java.desktop/java.awt.color "
             "java.desktop/sun.awt.image java.desktop/javax.swing java.desktop/java.awt "
             "java.base/java.util java.base/java.lang java.base/java.lang.reflect java.base/java.text "
             "java.desktop/java.awt.font java.base/jdk.internal.misc java.base/sun.nio.ch "
             "java.base/java.nio java.base/java.math java.base/java.util.concurrent java.base/java.net").split()


def find_java():
    """Find a Java 17+ runtime on macOS, Windows or Linux."""
    exe = "java.exe" if os.name == "nt" else "java"
    home = os.environ.get("JAVA_HOME")
    if home and os.path.exists(os.path.join(home, "bin", exe)):
        return os.path.join(home, "bin", exe)
    if sys.platform == "darwin" and os.path.exists("/usr/libexec/java_home"):
        try:
            out = subprocess.run(["/usr/libexec/java_home", "-v", "17+"], capture_output=True,
                                 text=True, timeout=10).stdout.strip()
            if out and os.path.exists(os.path.join(out, "bin", "java")):
                return os.path.join(out, "bin", "java")
        except Exception:
            pass
    if os.name == "nt":
        roots = [os.environ.get(v) for v in ("ProgramFiles", "ProgramW6432", "LOCALAPPDATA")]
        pats = ["Eclipse Adoptium/*/bin/java.exe", "Java/*/bin/java.exe", "Microsoft/jdk-*/bin/java.exe",
                "Zulu/*/bin/java.exe", "Amazon Corretto/*/bin/java.exe", "Programs/Eclipse Adoptium/*/bin/java.exe"]
        hits = []
        for r in filter(None, roots):
            for pat in pats:
                hits += glob.glob(os.path.join(r, pat))
        best = None
        for h in sorted(hits, reverse=True):
            v = java_version(h)
            if v and v >= 17 and (best is None or v > best[0]):
                best = (v, h)
        if best:
            return best[1]
    return shutil.which("java")


def java_version(java):
    try:
        p = subprocess.run([java, "-version"], capture_output=True, text=True, timeout=20)
        m = re.search(r'version "(\d+)(?:\.(\d+))?', p.stderr + p.stdout)
        if m:
            major = int(m.group(1))
            return int(m.group(2)) if major == 1 else major
    except Exception:
        pass
    return None


def find_forge_jar(folder):
    """Accepts the unpacked Forge folder, its parent, or Forge.app."""
    folder = os.path.expanduser(folder or "")
    if not folder:
        return None
    if os.path.isfile(folder) and folder.endswith(".jar"):
        return folder
    pats = ["forge-gui-desktop-*-jar-with-dependencies.jar", "forge-gui-desktop*.jar", "forge*.jar"]
    for depth in ("", "*/", "*/*/", "*/*/*/", "*/*/*/*/"):
        for pat in pats:
            hits = sorted(glob.glob(os.path.join(folder, depth + pat)))
            hits = [h for h in hits if "installer" not in os.path.basename(h).lower()]
            for h in hits:
                if os.path.isdir(os.path.join(os.path.dirname(h), "res")):
                    return h
    return None


def check_setup(forge_folder):
    """Returns (ok, list of messages)."""
    msgs, ok = [], True
    java = find_java()
    if not java:
        return False, ["Java was not found. Install Java 17 or newer (Temurin from adoptium.net), "
                       "then restart the app."]
    v = java_version(java)
    if v is None or v < 17:
        ok = False
        msgs.append(f"Java {v or '?'} found at {java}; Forge needs Java 17 or newer.")
    else:
        msgs.append(f"Java {v} found.")
    jar = find_forge_jar(forge_folder)
    if not jar:
        ok = False
        msgs.append("Forge was not found in that folder. Choose the folder you unpacked Forge into "
                    "(it contains a 'res' folder and forge.sh / forge.exe).")
    else:
        msgs.append(f"Forge found: {os.path.basename(jar)}")
    return ok, msgs


def write_dck(deck, deck_id, card_db, path):
    def fname(n):
        info = card_db.get(n) if card_db else None
        return info["forge_name"] if info else n
    lines = ["[metadata]", f"Name={deck_id}", "[Commander]"]
    lines += [f"1 {fname(c)}" for c in deck.commanders]
    lines.append("[Main]")
    lines += [f"{q} {fname(n)}" for q, n in deck.cards]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


class Cancelled(Exception):
    pass


HELPER_SRC = os.path.join(os.path.dirname(__file__), "java", "HandSim.java")
_helper_state = {}


def find_javac(java):
    exe = "javac.exe" if os.name == "nt" else "javac"
    cand = os.path.join(os.path.dirname(java or ""), exe)
    return cand if java and os.path.exists(cand) else shutil.which("javac")


def ensure_helper(jar, java, cache_dir, log=print):
    """Compile HandSim.java (prints opening hands) against the user's Forge jar, once.
    Returns the class folder, or None if that isn't possible (then plain 'sim' mode is used)."""
    key = os.path.basename(jar)
    if key in _helper_state:
        return _helper_state[key]
    out_dir = os.path.join(cache_dir, "handsim", re.sub(r"[^A-Za-z0-9._-]", "_", key))
    result = None
    if os.path.exists(os.path.join(out_dir, "HandSim.class")) and \
            os.path.getmtime(os.path.join(out_dir, "HandSim.class")) >= os.path.getmtime(HELPER_SRC):
        result = out_dir
    else:
        javac = find_javac(java)
        if not javac:
            log("Opening hands can't be recorded: Java's compiler (javac) is missing. Install a JDK, "
                "not a JRE (see README). Everything else works.")
        else:
            os.makedirs(out_dir, exist_ok=True)
            p = subprocess.run([javac, "--release", "17", "-nowarn", "-encoding", "UTF-8", "-cp", jar,
                                "-d", out_dir, HELPER_SRC], capture_output=True, text=True, timeout=180,
                               creationflags=0x08000000 if os.name == "nt" else 0)
            if p.returncode == 0:
                result = out_dir
                log("Opening-hand recorder is ready.")
            else:
                log("Opening hands can't be recorded with this Forge version (helper didn't compile); "
                    "using Forge's normal simulation mode.")
    _helper_state[key] = result
    return result


def disable_helper(jar):
    _helper_state[os.path.basename(jar)] = None


def run_pod(forge_folder, deck_dir, deck_files, game_clock, out_path, cancel_event=None,
            strong_ai=False, extra_timeout=180, helper_dir=None):
    """Play one 4-player Commander game. Forge's output goes to out_path; returns it as text."""
    java = find_java()
    jar = find_forge_jar(forge_folder)
    if not java or not jar:
        raise RuntimeError("Java or Forge not found - check Settings.")
    cmd = [java] + JAVA_ARGS
    for o in ADD_OPENS:
        cmd += ["--add-opens", o + "=ALL-UNNAMED"]
    if helper_dir:
        cmd += ["-cp", jar + os.pathsep + helper_dir, "HandSim", deck_dir, str(int(game_clock))]
        cmd += (["mc"] if strong_ai else []) + list(deck_files)
    else:
        cmd += ["-jar", jar, "sim", "-d"] + list(deck_files) + [
            "-D", deck_dir, "-f", "Commander", "-n", "1", "-c", str(int(game_clock))]
        if strong_ai:
            cmd += ["-mc", "on"]
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW on Windows
    deadline = time.time() + game_clock + extra_timeout
    with open(out_path, "w", encoding="utf-8", errors="replace") as out, \
            open(out_path + ".err", "w", encoding="utf-8", errors="replace") as err:
        p = subprocess.Popen(cmd, cwd=os.path.dirname(jar), stdout=out, stderr=err,
                             stdin=subprocess.DEVNULL, creationflags=flags)
        while p.poll() is None:
            if (cancel_event is not None and cancel_event.is_set()) or time.time() > deadline:
                p.kill()
                p.wait()
                if cancel_event is not None and cancel_event.is_set():
                    raise Cancelled()
                raise RuntimeError("Forge took too long and was stopped.")
            time.sleep(1)
    with open(out_path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if "Game Result" not in text:
        with open(out_path + ".err", encoding="utf-8", errors="replace") as f:
            tail = (f.read() or text)[-1500:]
        raise RuntimeError(f"Forge did not finish the game. Output tail:\n{tail}")
    try:
        if os.path.getsize(out_path + ".err") == 0:
            os.remove(out_path + ".err")
    except OSError:
        pass
    return text


# ----------------------------------------------------------------- log parsing
CAPTIONS = ("Game Outcome", "Match Result", "Sideboard", "Turn", "Mulligan", "Ante", "Draft",
            "Zone Change", "Player Control", "Damage", "Life", "Land", "Discard", "Combat",
            "Information", "Resolve Stack", "Add To Stack", "Replacement Effect", "Mana", "Phase")
LINE = re.compile(r"^(" + "|".join(re.escape(c) for c in CAPTIONS) + r"): (.*)$")
PLAYER = re.compile(r"Ai\(\d+\)-(D\d\d)")
TURN = re.compile(r"^Turn (\d+) \((.+)\)\s*$")
CARD_ID = re.compile(r"\s*\(\d+\)$")
OPENING = re.compile(r"^Opening Hand: Ai\(\d+\)-(D\d\d): ?(.*)$")
ATTACK = re.compile(r"^Ai\(\d+\)-(D\d\d) assigned (.+) to attack ")
CAST = re.compile(r"^Ai\(\d+\)-(D\d\d) cast (.+?)(?: targeting (.+))?$")
DAMAGE = re.compile(r"^(.+?) deals (\d+) (.*?)damage to (.+?)\.?$")
LIFE = re.compile(r"Ai\(\d+\)-(D\d\d) (-?\d+) > (-?\d+)")


@dataclass
class PlayerStats:
    deck: str
    place: int = 0
    points: float = 0
    won: bool = False
    eliminated: bool = False
    loss_reason: str = ""
    own_turns: int = 0
    mulligans: int = 0
    kept_size: int | None = None
    opening_hand: list | None = None
    casts_by_turn: dict = field(default_factory=dict)  # own turn -> spells cast during that turn
    lands_by_turn: dict = field(default_factory=dict)   # own turn -> lands played that turn
    first_spell_turn: int | None = None
    commander_turn: int | None = None
    spells_cast: int = 0
    cards_cast: list = field(default_factory=list)
    damage_dealt: int = 0
    damage_taken: int = 0
    damage_taken_from: dict = field(default_factory=dict)  # deck id -> dmg
    life: int = 40
    elim_round: int | None = None

    def lands_through(self, t):
        return sum(v for k, v in self.lands_by_turn.items() if k <= t)


@dataclass
class GameResult:
    players: dict          # deck id -> PlayerStats
    seat_order: list
    winner: str | None
    draw: bool
    rounds: int            # table rounds (each player had a turn)
    duration_ms: int = 0
    killers: dict = field(default_factory=dict)  # deck id -> deck id most responsible


def parse_game(stdout, deck_ids, commanders_of, cards_of):
    """deck_ids: seat order list; commanders_of/cards_of: deck id -> set of card names."""
    raw = [l.strip() for l in stdout.splitlines()]
    entries, hands = [], {}
    for l in raw:
        m = LINE.match(l)
        if m:
            entries.append((m.group(1), m.group(2)))
            continue
        h = OPENING.match(l)
        if h:
            hands[h.group(1)] = [c.strip() for c in h.group(2).split(";") if c.strip()]
    turn_nums = [int(TURN.match(msg).group(1)) for cap, msg in entries if cap == "Turn" and TURN.match(msg)]
    if len(turn_nums) >= 2 and turn_nums[0] > turn_nums[-1]:
        entries.reverse()

    P = {d: PlayerStats(deck=d) for d in deck_ids}
    for d, hand in hands.items():
        if d in P:
            P[d].opening_hand = hand
    owner_of_card, owner_of_object = {}, {}
    current, cur_own_turn = None, {}
    zero_idx, last_seen, last_damage_from = {}, {}, {}
    outcomes, last_table_turn = {}, 0
    draw = "ended in a Draw" in stdout or "Stopping slow match as draw" in stdout
    winner = None
    m = re.search(r"Ai\(\d+\)-(D\d\d) has won!", stdout)
    if m:
        winner = m.group(1)

    def owner_for(card):
        if card in owner_of_object:
            return owner_of_object[card]
        card = CARD_ID.sub("", card)
        if card in owner_of_card:
            return owner_of_card[card]
        owners = [d for d in deck_ids if card in cards_of.get(d, set())]
        return owners[0] if len(owners) == 1 else None

    for i, (cap, msg) in enumerate(entries):
        for d in PLAYER.findall(msg):
            if cap != "Game Outcome" and d in P:
                last_seen[d] = i
        if cap == "Turn":
            t = TURN.match(msg)
            if not t:
                continue
            pm = PLAYER.search(t.group(2))
            if pm and pm.group(1) in P:
                current = pm.group(1)
                P[current].own_turns += 1
                cur_own_turn[current] = P[current].own_turns
        elif cap == "Mulligan":
            pm = PLAYER.search(msg)
            if pm and pm.group(1) in P:
                if "mulliganed down" in msg:
                    P[pm.group(1)].mulligans += 1
                km = re.search(r"kept a hand of (\d+)", msg)
                if km:
                    P[pm.group(1)].kept_size = int(km.group(1))
        elif cap == "Combat":
            am = ATTACK.match(msg)
            if am and am.group(1) in P:
                for obj in re.findall(r"(.+?\(\d+\))(?:, | and |$)", am.group(2)):
                    owner_of_object[obj.strip()] = am.group(1)
        elif cap == "Land":
            pm = PLAYER.match(msg)
            if pm and pm.group(1) in P and " played " in msg:
                d = pm.group(1)
                t = cur_own_turn.get(d, 0)
                P[d].lands_by_turn[t] = P[d].lands_by_turn.get(t, 0) + 1
                owner_of_card[CARD_ID.sub("", msg.split(" played ", 1)[1].strip())] = d
        elif cap == "Add To Stack":
            c = CAST.match(msg)
            if c and c.group(1) in P:
                d, card = c.group(1), CARD_ID.sub("", c.group(2).strip())
                ps = P[d]
                owner_of_card[card] = d
                ps.spells_cast += 1
                ps.cards_cast.append(card)
                t = cur_own_turn.get(d, 0)
                if current == d and t:
                    ps.casts_by_turn.setdefault(t, []).append(card)
                if ps.first_spell_turn is None:
                    ps.first_spell_turn = max(t, 1)
                if ps.commander_turn is None and card in commanders_of.get(d, set()):
                    ps.commander_turn = max(t, 1)
        elif cap == "Damage":
            dm = DAMAGE.match(msg)
            if dm:
                tgt = PLAYER.search(dm.group(4))
                if tgt and tgt.group(1) in P and dm.group(4).strip().startswith("Ai("):
                    victim, amount = tgt.group(1), int(dm.group(2))
                    src_player = PLAYER.search(dm.group(1))
                    src = src_player.group(1) if src_player and dm.group(1).startswith("Ai(") \
                        else owner_for(dm.group(1).strip())
                    P[victim].damage_taken += amount
                    if src and src != victim and src in P:
                        P[src].damage_dealt += amount
                        P[victim].damage_taken_from[src] = P[victim].damage_taken_from.get(src, 0) + amount
                        last_damage_from[victim] = src
        elif cap == "Life":
            lm = LIFE.search(msg)
            if lm and lm.group(1) in P:
                d, new = lm.group(1), int(lm.group(3))
                P[d].life = new
                if new <= 0 and d not in zero_idx:
                    zero_idx[d] = i
        elif cap == "Game Outcome":
            pm = PLAYER.search(msg)
            if pm and pm.group(1) in P:
                outcomes[pm.group(1)] = msg.split(pm.group(0), 1)[1].strip()
            else:
                tm = re.match(r"^Turn (\d+)$", msg.strip())
                if tm:
                    last_table_turn = int(tm.group(1))

    # who is out?
    for d, ps in P.items():
        o = outcomes.get(d, "")
        if "has won" in o:
            ps.won = True
            winner = winner or d
        elif "lost" in o or "conceded" in o:
            ps.eliminated = True
            ps.loss_reason = o.replace("has ", "", 1)
        elif not outcomes and d in zero_idx:
            ps.eliminated = True
            ps.loss_reason = "lost because life total reached 0"
    if winner and winner in P:
        P[winner].won = True
        for d, ps in P.items():
            if d != winner:
                ps.eliminated = True
                ps.loss_reason = ps.loss_reason or "lost"
        draw = False

    # placement: winner, then survivors (by life), then eliminated (latest first)
    alive = [d for d in P if not P[d].eliminated and not P[d].won]
    out = [d for d in P if P[d].eliminated]
    out.sort(key=lambda d: zero_idx.get(d, last_seen.get(d, -1)), reverse=True)
    alive.sort(key=lambda d: P[d].life, reverse=True)
    order = ([winner] if winner else []) + alive + out
    pts_table = [4, 2, 1, 0]
    for place, d in enumerate(order, 1):
        P[d].place = place
        if draw:
            P[d].points = 1 if d in alive else 0
        else:
            P[d].points = pts_table[place - 1] if place <= 4 else 0
        P[d].elim_round = P[d].own_turns if P[d].eliminated else None

    killers = {}
    for d, ps in P.items():
        if ps.eliminated:
            k = last_damage_from.get(d)
            if not k and ps.damage_taken_from:
                k = max(ps.damage_taken_from, key=ps.damage_taken_from.get)
            killers[d] = k
    dur = re.search(r"ended in (\d+) ms", stdout)
    rounds = max((p.own_turns for p in P.values()), default=0)
    return GameResult(players=P, seat_order=list(deck_ids), winner=winner, draw=draw and not winner,
                      rounds=rounds, duration_ms=int(dur.group(1)) if dur else 0, killers=killers)
