# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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
