# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [3.3.0] - 2026-11-19

### Added
- Focus cards: name up to 10 cards you're unsure about and the report shows, for each, how often it
  was drawn and cast, on which turns, the damage it dealt, opponents it finished off, how games went
  with and without it, goldfish draw/cast rates, combos, EDHREC popularity and price, plus a
  game-by-game table. Claude's coaching notes give a keep / cut / test-more recommendation.

### Changed
- Opponents are now truly random: no colour-identity balancing and no commander rules. The app
  samples random pages from ~2,000 public decks and picks among them uniformly. Bracket, deck value
  matching and avoiding decks from your last 3 runs stay.

## [3.2.0] - 2026-11-19

### Added
- Settings → Appearance: theme (System, Light, Dark) and colour-blind friendly good/bad colours
  (Blue/orange, Blue/red) for the app and the PDF. Good and bad values are also marked ✓ and ✗.

### Changed
- "Never cast in testing" is only used, for the cards-to-reconsider list and for cut suggestions,
  once your deck has played at least 10 games; with fewer games it mostly means "never drawn".
- "Commander arrives late": when the goldfish shows the deck can cast its commander on curve, the
  report explains that the late casts are Forge's AI holding it back, and no longer suggests changes.
- Basic lands are no longer suggested (e.g. in the EDHREC comparison).

## [3.1.1] - 2026-11-19

### Fixed
- After a second run in the same browser session, the page could stay on the old report. Progress
  checks now retry after a hiccup (for example after the computer slept) instead of stopping, and
  the newest report always opens when a run finishes.
- The PDF couldn't be created when a single round of a game had very many spells (e.g. wheel or
  buyback decks). Repeated casts are grouped ("Capsize ×7"), very long rows are shortened, and if
  something still doesn't fit, the PDF is created without the key-moments appendix.
- If a report can't be shown or its PDF can't be created, the app now says so and offers to try
  again, instead of silently keeping the old report.

## [3.1.0] - 2026-11-19

### Changed
- Prices and deck values now use the cheapest paper printing of each card instead of Scryfall's
  default printing, so special printings no longer inflate a deck's value.
- Damage is split into combat and non-combat everywhere: "You vs. the field", key moments and the
  goldfish win check ("non-combat triggers & drain" instead of counting triggers as combat).
- The win check understands draw punishers (Nekusar, Underworld Dreams), extra draws and wheels.

### Fixed
- Key moments now explain repeated casts of the same spell (buyback, returned from the graveyard,
  bounced, flashback, commander recast). The Forge helper records how cards come back.
- Losses to commander damage name the commander instead of the last creature that dealt damage.

## [3.0.0] - 2026-11-19

### Added
- Import a deck by pasting an Archidekt (or Moxfield) link.
- Win check: the goldfish estimates the turn your deck wins alone (combat, commander damage,
  drain, poison, mill, combos) and where the damage comes from; lists "win the game" cards.
- Key moments: round-by-round summary of every game (your spells, life totals, knock-outs).
- Prices (Cardmarket EUR via Scryfall) on all suggestions; deck values in the report.
- Upgrade budget: highest-impact add/cut swaps that fit the amount you enter.
- Match opponents to your deck's value (±30%).
- EDHREC comparison: popular cards you don't play and your unusual picks.
- Play style: Forge AI personality for you and the opponents, mulligan rules for your deck.
- Sleep-proof runs: keeps the computer awake; sleep time no longer counts towards time limits.

### Changed
- Much faster runs: Forge starts once per worker and plays many games; stalled games end early
  (turn limit, no life change); games at once is chosen automatically.
- New interface following Apple's Human Interface Guidelines (system font, grouped sections,
  segmented controls, switches, settings sheet, dark mode). No more web fonts.
- New PDF design in the same style, using the bundled Inter font.

### Fixed
- Games stopped as draws were sometimes counted as wins.

## [2.3.0] - 2026-11-17

### Changed
- Combos are only looked up for your own deck; the field section now shows the opponents'
  counterspells and instant-speed removal. Runs start noticeably faster.
- Opponents are picked at random from a few hundred popular decks (more popular = more likely)
  instead of always the top of the list, so repeated runs face different decks.
- Decks you faced in your last 3 runs are rarely picked again.

## [2.2.0] - 2026-11-17

### Added
- "Combos and consistency" report section, so combo decks are judged fairly:
  - combos in your deck from Commander Spellbook, with links
  - goldfish simulation (6,000 solo games) of how fast each combo is assembled when played deliberately
  - consistency: keepable hands, turn 1–2 plays, commander on curve, screw and flood
  - Forge cross-check: combos Forge's AI had but didn't win with
  - combos one card away, combos above your bracket
  - the field's combos and counterspells
- New weak points: "Combo rarely comes together", "Forge didn't finish the combo",
  "Little interaction against combos", "Combo above your bracket", "Inconsistent opening hands",
  "Mana screw risk", "Flood risk".
- Claude coaching notes now receive the combo data.

## [2.1.0] - 2026-11-17

### Added
- Report summary of your deck's kept opening hand in every game (via a small helper compiled
  against your Forge copy) and whether it made a non-land play on its turn 1 and turn 2.
- New weak points: "No early plays" and "Unbalanced opening hands".

### Changed
- Forge games run headless (no Dock/taskbar icons).
- README: Forge's release download is now named `forge-installer-<version>.tar.bz2`.

### Fixed
- The "kept a hand" log line was counted as a mulligan.
- Damage from tokens and creatures is now credited to the right player.
- Deck-makeup warnings are skipped when card data couldn't be looked up.

## [2.0.0] - 2026-11-17

### Added
- PDF report for every test run (default download), plus Markdown and JSON.
- Windows support: `start-windows.bat` launcher, Java detection in common install folders.
- Optional Moxfield opponent search (needs a Moxfield-approved User-Agent).
- Opponent decks are picked by popularity with few repeated colour identities.
- Deck name field, "Show in folder" button, stop button now ends running Forge games.

### Changed
- Renamed from "Pod Tester" to **MTG Commander Deck Tester**.
- Launchers create a private Python environment (`.venv`) and install dependencies automatically.
- Opponent search no longer uses recently updated decks.

### Fixed
- Cards wrongly tagged as commander on deck sites (e.g. Cultivate) are moved back into the deck.
- Copies of your own deck are no longer picked as opponents.
- Deck names containing `|` no longer break the Markdown report tables.

## [1.0.0] - 2026-11-17

- First version: Archidekt decklists, Forge AI tournaments in pods of four, weak-point analysis,
  optional Claude coaching notes.
