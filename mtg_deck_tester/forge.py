"""Run Forge's headless simulation mode and parse its game logs."""
from __future__ import annotations
import glob
import hashlib
import os
import re
import shutil
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field

JAVA_ARGS = [
    "-Xmx3072m", "-Dio.netty.tryReflectionSetAccessible=true", "-Dfile.encoding=UTF-8",
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
    # the compiled helper is cached per Forge jar AND per helper source content, so an app update
    # always rebuilds it (file dates can't be trusted after copying/unzipping)
    with open(HELPER_SRC, "rb") as f:
        src_hash = hashlib.sha1(f.read()).hexdigest()[:12]
    out_dir = os.path.join(cache_dir, "handsim", re.sub(r"[^A-Za-z0-9._-]", "_", key) + "-" + src_hash)
    result = None
    if os.path.exists(os.path.join(out_dir, "HandSim.class")):
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
    budget = game_clock + extra_timeout  # seconds of awake time
    with open(out_path, "w", encoding="utf-8", errors="replace") as out, \
            open(out_path + ".err", "w", encoding="utf-8", errors="replace") as err:
        p = subprocess.Popen(cmd, cwd=os.path.dirname(jar), stdout=out, stderr=err,
                             stdin=subprocess.DEVNULL, creationflags=flags)
        last = time.time()
        while p.poll() is None:
            now = time.time()
            budget -= min(now - last, 5)  # a sleeping computer doesn't use up the time limit
            last = now
            if (cancel_event is not None and cancel_event.is_set()) or budget < 0:
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


class ForgeSession:
    """One running Forge (HandSim helper) that plays many games, so Forge starts only once.
    Restarted automatically after a crash and every RESTART_EVERY games."""
    RESTART_EVERY = 12
    _open = set()
    _lock = threading.Lock()

    @classmethod
    def close_all(cls):
        with cls._lock:
            sessions = list(cls._open)
        for s in sessions:
            s.close()

    def __init__(self, forge_folder, helper_dir, log_dir, log=print):
        self.java = find_java()
        self.jar = find_forge_jar(forge_folder)
        self.helper_dir = helper_dir
        self.log_dir = log_dir
        self.log = log
        self.proc = None
        self.games = 0
        self.lines = queue.Queue()

    def _reader(self, proc):
        for line in proc.stdout:
            self.lines.put(line.rstrip("\n"))
        self.lines.put(None)

    def start(self, cancel_event=None):
        cmd = [self.java] + JAVA_ARGS
        for o in ADD_OPENS:
            cmd += ["--add-opens", o + "=ALL-UNNAMED"]
        cmd += ["-cp", self.jar + os.pathsep + self.helper_dir, "HandSim"]
        err = open(os.path.join(self.log_dir, f"forge-session-{id(self)}.err"), "a", encoding="utf-8", errors="replace")
        self.lines = queue.Queue()
        self.proc = subprocess.Popen(cmd, cwd=os.path.dirname(self.jar), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=err, text=True, encoding="utf-8", errors="replace", bufsize=1,
                                     creationflags=0x08000000 if os.name == "nt" else 0)
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()
        with ForgeSession._lock:
            ForgeSession._open.add(self)
        self.games = 0
        if self._wait_for(lambda l: l == "@@READY", 300, cancel_event) is None:
            self.close()
            raise RuntimeError("Forge did not start (see forge-session .err file in the logs folder).")

    def _wait_for(self, match, budget, cancel_event):
        last = time.time()
        while budget > 0:
            if cancel_event is not None and cancel_event.is_set():
                self.close()
                raise Cancelled()
            try:
                line = self.lines.get(timeout=1)
            except queue.Empty:
                line = ""
            now = time.time()
            budget -= min(now - last, 5)  # sleep doesn't count
            last = now
            if line is None:
                return None  # process ended
            if line and match(line):
                return line
        return None

    def play(self, deck_dir, specs, out_path, clock, max_turns, stall_turns, strong_ai, cancel_event=None):
        """specs: list of 'file.dck|Profile|minL,maxL,cheap,maxMull'. Returns the game log text."""
        if self.proc is None or self.proc.poll() is not None or self.games >= self.RESTART_EVERY:
            self.close()
            self.start(cancel_event)
        gid = f"g{self.games}"
        self.games += 1
        cmd = "\t".join(["GAME", gid, out_path, deck_dir, str(int(clock)), str(int(max_turns)), str(int(stall_turns)),
                         "1" if strong_ai else "0"] + list(specs))
        try:
            self.proc.stdin.write(cmd + "\n")
            self.proc.stdin.flush()
        except OSError:
            self.close()
            raise RuntimeError("Forge stopped unexpectedly.")
        line = self._wait_for(lambda l: l.startswith(("@@DONE " + gid, "@@ERROR " + gid)), clock + 240, cancel_event)
        if line is None:
            self.close()
            raise RuntimeError("Forge took too long or stopped; it will be restarted for the next game.")
        if line.startswith("@@ERROR"):
            raise RuntimeError("Forge: " + line.split(" ", 2)[-1][:300])
        with open(out_path, encoding="utf-8", errors="replace") as f:
            return f.read()

    def close(self):
        with ForgeSession._lock:
            ForgeSession._open.discard(self)
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.stdin.write("QUIT\n")
                p.stdin.flush()
                p.wait(timeout=10)
            except Exception:
                p.kill()


def auto_workers():
    """How many Forge games to run at once: leave a core free, about 3 GB of memory per game."""
    cores = os.cpu_count() or 2
    mem_gb = None
    try:
        if sys.platform == "darwin":
            mem_gb = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
                                        timeout=5).stdout.strip()) / 2 ** 30
        elif os.name == "nt":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = MS()
            ms.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            mem_gb = ms.ullTotalPhys / 2 ** 30
        else:
            with open("/proc/meminfo") as f:
                mem_gb = int(f.readline().split()[1]) / 2 ** 20
    except Exception:
        pass
    by_mem = int((mem_gb - 4) // 3) if mem_gb else 2
    return max(1, min(cores - 1, by_mem, 6))


# ----------------------------------------------------------------- log parsing
CAPTIONS = ("Game Outcome", "Match Result", "Sideboard", "Turn", "Mulligan", "Ante", "Draft",
            "Zone Change", "Player Control", "Damage", "Life", "Land", "Discard", "Combat",
            "Information", "Resolve Stack", "Add To Stack", "Replacement Effect", "Mana", "Phase")
LINE = re.compile(r"^(" + "|".join(re.escape(c) for c in CAPTIONS) + r"): (.*)$")
PLAYER = re.compile(r"Ai\(\d+\)-(D\d\d)")
TURN = re.compile(r"^Turn (\d+) \((.+)\)\s*$")
CARD_ID = re.compile(r"\s*\(\d+\)$")
OPENING = re.compile(r"^Opening Hand: Ai\(\d+\)-(D\d\d): ?(.*)$")
MOVED = re.compile(r"^\[Moved\] Ai\(\d+\)-(D\d\d): (.+?) from (\w+) to (\w+)$")
MOVE_REASON = {("Stack", "Hand"): "returned to hand as it resolved (e.g. buyback)",
               ("Graveyard", "Hand"): "returned from the graveyard to hand",
               ("Battlefield", "Hand"): "bounced back to hand",
               ("Exile", "Hand"): "returned from exile to hand",
               ("Graveyard", "Stack"): "cast from the graveyard (e.g. flashback)",
               ("Exile", "Stack"): "cast from exile",
               ("Library", "Stack"): "cast from the library",
               ("Graveyard", "Battlefield"): "returned from the graveyard to the battlefield"}
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
    damage_dealt_combat: int = 0
    damage_dealt_noncombat: int = 0
    damage_taken_combat: int = 0
    damage_taken_noncombat: int = 0
    recasts: dict = field(default_factory=dict)  # card -> how often it was cast again, and how it came back
    # per-card details (recorded for the focus deck only)
    cast_log: list = field(default_factory=list)      # [{"card", "round", "turn"}] every cast, in order
    card_damage: dict = field(default_factory=dict)   # card -> {"combat": n, "noncombat": n} to players
    card_kills: list = field(default_factory=list)    # [{"card", "victim", "round"}] knock-outs credited to a card
    lands_played: list = field(default_factory=list)  # land names played
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
    timeline: list = field(default_factory=list)  # key moments of the focus deck per table round


def parse_game(stdout, deck_ids, commanders_of, cards_of, focus="D01"):
    """deck_ids: seat order list; commanders_of/cards_of: deck id -> set of card names.
    focus: the deck whose key moments are recorded round by round."""
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
    draw = ("ended in a Draw" in stdout or "Stopping slow match as draw" in stdout
            or "Stopping stalled match as draw" in stdout)
    winner = None
    m = re.search(r"Ai\(\d+\)-(D\d\d) has won!", stdout)
    if m and not draw:
        winner = m.group(1)

    def owner_for(card):
        if card in owner_of_object:
            return owner_of_object[card]
        card = CARD_ID.sub("", card)
        if card in owner_of_card:
            return owner_of_card[card]
        owners = [d for d in deck_ids if card in cards_of.get(d, set())]
        return owners[0] if len(owners) == 1 else None

    # key moments for the focus deck, one entry per table round
    timeline, rnd, first_seat, prev_rel = [], 0, None, None
    seat_of = {}
    for m0 in re.finditer(r"Ai\((\d+)\)-(D\d\d)", stdout):
        seat_of.setdefault(m0.group(2), int(m0.group(1)))
    n_seats = max(len(seat_of), 1)
    round_of_index = {}
    killer_card = {}
    cast_count, last_move = {}, {}   # (deck, card) -> casts so far / how it last came back

    def new_round():
        timeline.append({"round": rnd, "cast": [], "cast_detail": [], "lands": 0, "dealt": 0, "taken": 0,
                         "dealt_combat": 0, "dealt_other": 0, "taken_combat": 0, "taken_other": 0,
                         "events": [], "life": {}})

    for i, (cap, msg) in enumerate(entries):
        round_of_index[i] = rnd
        if cap == "Turn":
            tm0 = TURN.match(msg)
            pm0 = PLAYER.search(tm0.group(2)) if tm0 else None
            if pm0:
                # a new round starts when the turn passes "back around the table" in seating order,
                # so it keeps working after the player who went first has been knocked out
                seat = seat_of.get(pm0.group(1), 0)
                if first_seat is None:
                    first_seat = seat
                rel = (seat - first_seat) % n_seats
                if prev_rel is None or rel < prev_rel:
                    if timeline:
                        timeline[-1]["life"] = {d: P[d].life for d in P}
                    rnd += 1
                    new_round()
                    round_of_index[i] = rnd
                prev_rel = rel
        T = timeline[-1] if timeline else None
        if T is not None and focus in P:
            if cap == "Land" and msg.startswith(f"Ai(") and PLAYER.match(msg) and PLAYER.match(msg).group(1) == focus \
                    and " played " in msg:
                T["lands"] += 1
            elif cap == "Add To Stack":
                c0 = CAST.match(msg)
                if c0 and c0.group(1) == focus:
                    card0 = CARD_ID.sub("", c0.group(2).strip())
                    T["cast"].append(card0)
                    k = cast_count.get((focus, card0), 0)
                    if k == 0:
                        T["cast_detail"].append(card0)
                    elif card0 in commanders_of.get(focus, set()):
                        T["cast_detail"].append(f"{card0} (cast {k + 1}× – recast from the command zone)")
                    else:
                        why = last_move.pop((focus, card0), None) or "how it came back isn't in Forge's log"
                        T["cast_detail"].append(f"{card0} (cast {k + 1}× – {why})")
                    if card0 in commanders_of.get(focus, set()):
                        T["events"].append(f"You cast your commander {card0}")
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
        elif cap == "Zone Change":
            mv = MOVED.match(msg)
            if mv and mv.group(1) in P:
                why = MOVE_REASON.get((mv.group(3), mv.group(4)))
                if why:
                    last_move[(mv.group(1), CARD_ID.sub("", mv.group(2).strip()))] = why
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
                land = CARD_ID.sub("", msg.split(" played ", 1)[1].strip())
                owner_of_card[land] = d
                if d == focus:
                    P[d].lands_played.append(land)
        elif cap == "Add To Stack":
            c = CAST.match(msg)
            if c and c.group(1) in P:
                d, card = c.group(1), CARD_ID.sub("", c.group(2).strip())
                ps = P[d]
                owner_of_card[card] = d
                n_before = cast_count.get((d, card), 0)
                cast_count[(d, card)] = n_before + 1
                if n_before and card not in commanders_of.get(d, set()):
                    ps.recasts[card] = ps.recasts.get(card, 0) + 1
                ps.spells_cast += 1
                ps.cards_cast.append(card)
                t = cur_own_turn.get(d, 0)
                if current == d and t:
                    ps.casts_by_turn.setdefault(t, []).append(card)
                if d == focus:
                    ps.cast_log.append({"card": card, "round": rnd, "turn": t, "own_turn": current == d})
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
                    combat = "non-combat" not in dm.group(3)
                    src_player = PLAYER.search(dm.group(1))
                    src = src_player.group(1) if src_player and dm.group(1).startswith("Ai(") \
                        else owner_for(dm.group(1).strip())
                    P[victim].damage_taken += amount
                    if combat:
                        P[victim].damage_taken_combat += amount
                    else:
                        P[victim].damage_taken_noncombat += amount
                    if timeline:
                        kind = "combat" if combat else "other"
                        if victim == focus:
                            timeline[-1]["taken"] += amount
                            timeline[-1]["taken_" + kind] += amount
                        elif src == focus:
                            timeline[-1]["dealt"] += amount
                            timeline[-1]["dealt_" + kind] += amount
                    if src == focus and src != victim:
                        cd0 = P[focus].card_damage.setdefault(CARD_ID.sub("", dm.group(1).strip()),
                                                              {"combat": 0, "noncombat": 0})
                        cd0["combat" if combat else "noncombat"] += amount
                    if src and src != victim and src in P:
                        killer_card[victim] = CARD_ID.sub("", dm.group(1).strip()) + ("" if combat else " (non-combat)")
                        P[src].damage_dealt += amount
                        if combat:
                            P[src].damage_dealt_combat += amount
                        else:
                            P[src].damage_dealt_noncombat += amount
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
        if "has won" in o and not draw:
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
    # finish the timeline: last life totals, knock-outs
    if timeline:
        timeline[-1]["life"] = {d: P[d].life for d in P}
        for d, ps in P.items():
            if not ps.eliminated:
                continue
            at = zero_idx.get(d, last_seen.get(d))
            r = round_of_index.get(at, rnd) if at is not None else rnd
            r = max(1, min(r, len(timeline)))
            who = killers.get(d)
            how = ps.loss_reason.replace("lost because ", "").replace("lost due to ", "")
            by = f" by {killer_card[d]}" if d in killer_card and who and \
                any(k in how for k in ("life total", "poison")) else ""
            if "21 damage" in how and who and commanders_of.get(who):
                by = f" by {sorted(commanders_of[who])[0]}"
                how = "21 commander damage"
            if who == focus and d != focus and d in killer_card and \
                    any(k in how for k in ("life total", "poison")):
                P[focus].card_kills.append({"card": killer_card[d].replace(" (non-combat)", ""), "victim": d,
                                            "round": r})
            elif who == focus and "21 damage" in ps.loss_reason:
                P[focus].card_kills.append({"card": sorted(commanders_of.get(focus, {"your commander"}))[0],
                                            "victim": d, "round": r})
            if d == focus:
                txt = f"You were knocked out{by} ({how})"
            else:
                txt = f"{d} knocked out{by}"
            timeline[r - 1]["events"].append({"text": txt, "deck": d, "killer": who})
        if winner:
            timeline[-1]["events"].append({"text": f"{winner} won", "deck": winner})
    for T in timeline:
        T["events"] = [e if isinstance(e, dict) else {"text": e} for e in T["events"]]

    dur = re.search(r"ended in (\d+) ms", stdout)
    rounds = max((p.own_turns for p in P.values()), default=0)
    return GameResult(players=P, seat_order=list(deck_ids), winner=winner, draw=draw and not winner,
                      rounds=rounds, duration_ms=int(dur.group(1)) if dur else 0, killers=killers,
                      timeline=timeline)
