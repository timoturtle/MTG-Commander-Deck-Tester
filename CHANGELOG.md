# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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
