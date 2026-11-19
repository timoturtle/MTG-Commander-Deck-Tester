// MTG Commander Deck Tester - helper around Forge's game engine (MIT License, part of this project).
//
// It is compiled on the user's machine against their own copy of Forge (see forge.py) and adds,
// compared with Forge's built-in "sim" mode:
//   * one Forge session plays many games (no 10-20 s start-up per game)
//   * every player's kept opening hand is written to the log ("Opening Hand: ...")
//   * per-deck AI personality (Forge's AI profiles) and optional mulligan rules
//   * stalled games end early (turn limit, no life change for many turns)
//   * the time limit only counts time the computer is awake
//
// Protocol (one line per command on stdin, fields separated by TAB):
//   GAME  id  outFile  deckDir  clockSec  maxTurns  stallTurns  monteCarlo(0/1)  deck1 ... deckN
//   QUIT
// where each deck is  file.dck|AiProfile|minLands,maxLands,needCheap,maxMulligans  (rules optional).
// Replies on stdout: "@@READY", "@@DONE id", "@@ERROR id message". Other stdout lines are noise.

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.PrintStream;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.List;

import com.google.common.eventbus.Subscribe;

import forge.GuiDesktop;
import forge.deck.Deck;
import forge.deck.io.DeckSerializer;
import forge.ai.LobbyPlayerAi;
import forge.ai.PlayerControllerAi;
import forge.game.Game;
import forge.game.GameEndReason;
import forge.game.GameLogEntry;
import forge.game.GameRules;
import forge.game.GameType;
import forge.game.Match;
import forge.game.card.Card;
import forge.game.event.GameEvent;
import forge.game.player.Player;
import forge.game.player.RegisteredPlayer;
import forge.game.zone.ZoneType;
import forge.gui.GuiBase;
import forge.model.FModel;

public class HandSim {

    /** Optional mulligan rules for one deck. */
    static final class MullRule {
        final int minLands, maxLands, maxMulligans;
        final boolean needCheap;

        MullRule(String spec) {
            String[] p = spec.split(",");
            minLands = Integer.parseInt(p[0]);
            maxLands = Integer.parseInt(p[1]);
            needCheap = p[2].equals("1");
            maxMulligans = Integer.parseInt(p[3]);
        }
    }

    /** Forge AI player whose keep/mulligan decision follows MullRule. */
    static final class RuledAi extends LobbyPlayerAi {
        private final MullRule rule;

        RuledAi(String name, MullRule rule) {
            super(name, null);
            this.rule = rule;
        }

        @Override
        public Player createIngamePlayer(Game game, final int id) {
            Player ai = new Player(getName(), game, id);
            final MullRule r = rule;
            PlayerControllerAi pc = new PlayerControllerAi(game, ai, this) {
                private int mulligans = 0;

                @Override
                public boolean mulliganKeepHand(Player firstPlayer, int cardsToReturn) {
                    if (r == null) {
                        return super.mulliganKeepHand(firstPlayer, cardsToReturn);
                    }
                    if (mulligans >= r.maxMulligans) {
                        return true;
                    }
                    int lands = 0;
                    boolean cheap = false;
                    for (Card c : getPlayer().getCardsIn(ZoneType.Hand)) {
                        if (c.isLand()) {
                            lands++;
                        } else if (c.getCMC() <= 2) {
                            cheap = true;
                        }
                    }
                    boolean keep = lands >= r.minLands && lands <= r.maxLands && (cheap || !r.needCheap);
                    if (!keep) {
                        mulligans++;
                    }
                    return keep;
                }
            };
            ai.setFirstController(pc);
            return ai;
        }
    }

    /** Writes opening hands and stops stalled games. */
    public static final class Watcher {
        private final Game game;
        private final PrintStream out;
        private final int maxTurns, stallTurns;
        private boolean printed = false;
        private int turns = 0, lastChangeTurn = 0;
        private String lastState = "";
        volatile boolean stalled = false;

        Watcher(Game game, PrintStream out, int maxTurns, int stallTurns) {
            this.game = game;
            this.out = out;
            this.maxTurns = maxTurns;
            this.stallTurns = stallTurns;
        }

        @Subscribe
        public void onEvent(GameEvent ev) {
            if (!ev.getClass().getSimpleName().equals("GameEventTurnBegan")) {
                return;
            }
            if (!printed) {
                printed = true;
                for (Player p : game.getPlayers()) {
                    List<String> names = new ArrayList<>();
                    for (Card c : p.getCardsIn(ZoneType.Hand)) {
                        names.add(c.getName());
                    }
                    out.println("Opening Hand: " + p.getName() + ": " + String.join("; ", names));
                }
            }
            turns++;
            StringBuilder sb = new StringBuilder();
            for (Player p : game.getPlayers()) {
                sb.append(p.getLife()).append('/').append(p.getPoisonCounters()).append(' ');
            }
            String state = sb.toString();
            if (!state.equals(lastState)) {
                lastState = state;
                lastChangeTurn = turns;
            }
            boolean tooLong = maxTurns > 0 && turns > maxTurns;
            boolean noProgress = stallTurns > 0 && turns > 20 && turns - lastChangeTurn >= stallTurns;
            if ((tooLong || noProgress) && !stalled) {
                stalled = true;
                out.println("Stopping stalled match as draw: " + (tooLong ? "turn limit" : "no life change for " + stallTurns + " turns"));
                game.setGameOver(GameEndReason.Draw);
            }
        }
    }

    static void playGame(String[] f) throws Exception {
        String outFile = f[2], deckDir = f[3];
        int clock = Integer.parseInt(f[4]), maxTurns = Integer.parseInt(f[5]), stallTurns = Integer.parseInt(f[6]);
        boolean monteCarlo = f[7].equals("1");
        try (PrintStream out = new PrintStream(new FileOutputStream(outFile), true, "UTF-8")) {
            out.println("Simulation mode");
            List<RegisteredPlayer> players = new ArrayList<>();
            for (int k = 8; k < f.length; k++) {
                String[] spec = f[k].split("\\|", -1);
                Deck d = DeckSerializer.fromFile(new File(deckDir, spec[0]));
                if (d == null) {
                    throw new IllegalArgumentException("Could not load deck " + spec[0]);
                }
                int seat = players.size() + 1;
                MullRule rule = spec.length > 2 && !spec[2].isEmpty() ? new MullRule(spec[2]) : null;
                RuledAi lobby = new RuledAi("Ai(" + seat + ")-" + d.getName(), rule);
                if (spec.length > 1 && !spec[1].isEmpty()) {
                    lobby.setAiProfile(spec[1]);
                }
                RegisteredPlayer rp = RegisteredPlayer.forCommander(d);
                rp.setPlayer(lobby);
                players.add(rp);
            }
            GameRules rules = new GameRules(GameType.Commander);
            rules.setAppliedVariants(EnumSet.of(GameType.Commander));
            rules.setSimTimeout(clock);
            Match match = new Match(rules, players, "Test");
            Game game = match.createGame();
            game.setNoGUIUser();
            if (monteCarlo) {
                try {
                    Game.class.getField("AI_FLAT_MONTE_CARLO").setBoolean(game, true);
                } catch (Exception ignored) {
                    // not available in this Forge version
                }
            }
            Watcher watcher = new Watcher(game, out, maxTurns, stallTurns);
            game.subscribeToEvents(watcher);

            long start = System.currentTimeMillis();
            Thread t = new Thread(() -> {
                try {
                    match.startGame(game);
                } catch (Throwable e) {
                    e.printStackTrace(out);
                }
            }, "game");
            t.setDaemon(true);
            t.start();
            // time limit counted only while the computer is awake: big clock jumps (sleep) are ignored
            long awakeMs = 0, last = System.nanoTime();
            boolean timedOut = false;
            while (t.isAlive()) {
                t.join(1000);
                long now = System.nanoTime();
                awakeMs += Math.min((now - last) / 1_000_000L, 5000L);
                last = now;
                if (awakeMs > clock * 1000L && !game.isGameOver()) {
                    out.println("Stopping slow match as draw");
                    timedOut = true;
                    game.setGameOver(GameEndReason.Draw);
                    t.interrupt();
                    t.join(30000);
                    break;
                }
            }
            long ms = System.currentTimeMillis() - start;
            List<GameLogEntry> log = game.getGameLog().getLogEntries(null);
            Collections.reverse(log);
            for (GameLogEntry l : log) {
                out.println(l);
            }
            if (timedOut || watcher.stalled || !game.isGameOver() || game.getOutcome() == null
                    || game.getOutcome().isDraw()) {
                out.printf("%nGame Result: Game 1 ended in a Draw! Took %d ms.%n", ms);
            } else {
                out.printf("%nGame Result: Game 1 ended in %d ms. %s has won!%n%n", ms,
                        game.getOutcome().getWinningLobbyPlayer().getName());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        System.setProperty("java.awt.headless", "true");
        PrintStream protocol = new PrintStream(new FileOutputStream(java.io.FileDescriptor.out), true, "UTF-8");
        // Forge prints debug lines to System.out; send them to stderr so the protocol stays clean
        System.setOut(System.err);
        GuiBase.setInterface(new GuiDesktop());
        FModel.initialize(null, null);
        protocol.println("@@READY");
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        String line;
        while ((line = in.readLine()) != null) {
            String[] f = line.split("\t");
            if (f[0].equals("QUIT")) {
                break;
            }
            if (!f[0].equals("GAME") || f.length < 12) {
                continue;
            }
            try {
                playGame(f);
                protocol.println("@@DONE " + f[1]);
            } catch (Throwable e) {
                protocol.println("@@ERROR " + f[1] + " " + String.valueOf(e).replace('\n', ' '));
            }
        }
        System.exit(0);
    }
}
