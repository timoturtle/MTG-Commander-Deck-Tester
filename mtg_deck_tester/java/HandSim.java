// MTG Commander Deck Tester - small helper around Forge's simulation mode.
// Plays one Commander game exactly like "forge sim -f Commander -n 1", and additionally
// prints every player's opening hand (the hand kept after mulligans) as
//   Opening Hand: Ai(1)-D01: Card A; Card B; ...
// It is compiled on the user's machine against their own Forge jar (see forge.py).
// Usage: java -cp <forge.jar><sep><dir> HandSim <deckDir> <clockSeconds> [mc] deck1.dck deck2.dck ...

import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import com.google.common.eventbus.Subscribe;

import forge.GuiDesktop;
import forge.deck.Deck;
import forge.deck.io.DeckSerializer;
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
import forge.player.GamePlayerUtil;
import forge.view.TimeLimitedCodeBlock;

public class HandSim {

    public static class HandListener {
        private final Game game;
        private boolean printed = false;

        HandListener(Game game) {
            this.game = game;
        }

        @Subscribe
        public void onEvent(GameEvent ev) {
            if (printed || !ev.getClass().getSimpleName().equals("GameEventTurnBegan")) {
                return;
            }
            printed = true;  // first turn begins: every hand is the kept opening hand
            for (Player p : game.getPlayers()) {
                List<String> names = new ArrayList<>();
                for (Card c : p.getCardsIn(ZoneType.Hand)) {
                    names.add(c.getName());
                }
                System.out.println("Opening Hand: " + p.getName() + ": " + String.join("; ", names));
            }
        }
    }

    public static void main(String[] args) throws Exception {
        System.setProperty("java.awt.headless", "true");
        GuiBase.setInterface(new GuiDesktop());
        FModel.initialize(null, null);
        System.out.println("Simulation mode");

        String deckDir = args[0];
        int clock = Integer.parseInt(args[1]);
        boolean monteCarlo = false;
        List<RegisteredPlayer> players = new ArrayList<>();
        int i = 1;
        for (int k = 2; k < args.length; k++) {
            if (args[k].equals("mc")) {
                monteCarlo = true;
                continue;
            }
            Deck d = DeckSerializer.fromFile(new File(deckDir, args[k]));
            if (d == null) {
                System.out.println("Could not load deck - " + args[k] + ", match cannot start");
                System.exit(2);
            }
            RegisteredPlayer rp = RegisteredPlayer.forCommander(d);
            rp.setPlayer(GamePlayerUtil.createAiPlayer("Ai(" + i + ")-" + d.getName(), i - 1));
            players.add(rp);
            i++;
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
                // older Forge: option not available
            }
        }
        game.subscribeToEvents(new HandListener(game));

        long start = System.currentTimeMillis();
        try {
            TimeLimitedCodeBlock.runWithTimeout(() -> match.startGame(game), clock, TimeUnit.SECONDS);
        } catch (TimeoutException e) {
            System.out.println("Stopping slow match as draw");
        } catch (Exception | StackOverflowError e) {
            e.printStackTrace();
        } finally {
            game.setGameOver(GameEndReason.Draw);
        }
        long ms = System.currentTimeMillis() - start;

        List<GameLogEntry> log = game.getGameLog().getLogEntries(null);
        Collections.reverse(log);
        for (GameLogEntry l : log) {
            System.out.println(l);
        }
        if (game.getOutcome().isDraw()) {
            System.out.printf("%nGame Result: Game 1 ended in a Draw! Took %d ms.%n", ms);
        } else {
            System.out.printf("%nGame Result: Game 1 ended in %d ms. %s has won!%n%n", ms,
                    game.getOutcome().getWinningLobbyPlayer().getName());
        }
        System.out.flush();
        System.exit(0);
    }
}
