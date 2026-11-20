# Third-party software, services and notices

MTG Commander Deck Tester's own code is released under the [MIT License](LICENSE).
It bundles no third-party code or card data; the only bundled third-party files are the Inter font
files (see Fonts). Everything else below is installed separately, downloaded by the user, or
contacted over the internet while the app runs.

## Python packages (installed automatically from PyPI by the start scripts)

| Package | Used for | License |
|---|---|---|
| [ReportLab](https://pypi.org/project/reportlab/) | Creating PDF reports | BSD license (see the package's `LICENSE.txt`) |
| [certifi](https://pypi.org/project/certifi/) | Trusted HTTPS certificates | Mozilla Public License 2.0 |

Everything else is from the Python standard library (Python Software Foundation License).

## Programs you install yourself (not included in this repository)

| Program | Used for | License |
|---|---|---|
| [Forge](https://github.com/Card-Forge/forge) | Rules engine and AI that plays the games | GNU General Public License v3.0 |
| Java 17+, e.g. [Eclipse Temurin](https://adoptium.net) | Runs Forge | GPLv2 with Classpath Exception |
| [Python](https://www.python.org) 3.9+ | Runs this app | Python Software Foundation License |

This app starts Forge as a separate program and reads its text output. It does not include or
modify Forge's code. For opening hands, mulligan rules, AI profiles and faster runs, the small helper `mtg_deck_tester/java/HandSim.java`
(part of this project, MIT-licensed, which is compatible with the GPL) is compiled on your own
computer against your own copy of Forge and runs together with it there; no compiled combination
of the two is distributed. Forge's license applies to Forge itself.

## Online services

| Service | Used for | Notes |
|---|---|---|
| [Scryfall API](https://scryfall.com/docs/api) | Card names, colour identity, card types, prices (Cardmarket EUR / USD) | Used per Scryfall's API guidelines: identifying User-Agent, its documented rate limits (2 requests per second for searches and collection lookups, 10 for other endpoints), pausing when asked (HTTP 429), and a local cache. Card data is © Wizards of the Coast. |
| [Commander Spellbook](https://commanderspellbook.com) | Finding combos in decklists | Public API of its open-source backend ([commander-spellbook-backend](https://github.com/SpaceCowMedia/commander-spellbook-backend)), used at a low request rate with local caching. Combo data belongs to Commander Spellbook and its contributors. |
| [EDHREC](https://edhrec.com) | Cards commonly played with your commander | No official API; the app reads the public JSON the EDHREC website uses (json.edhrec.com), at a low request rate with a one-week cache. Data belongs to EDHREC. |
| [Archidekt](https://archidekt.com) | Finding popular public decks, importing decks by link | Public but undocumented API, used at a low request rate. Deck lists belong to their authors. |
| [Moxfield](https://moxfield.com) | Finding popular public decks (optional) | Off by default. Moxfield's terms don't allow automated access without permission; the feature only runs with a User-Agent that Moxfield issued to you (ask support@moxfield.com). |
| [Claude API](https://www.anthropic.com/api) by Anthropic | Optional coaching notes | Only with your own API key; usage is billed to your account and subject to Anthropic's terms. |

## Fonts

| Font | Used for | License | Location |
|---|---|---|---|
| [Inter](https://github.com/rsms/inter) 4.1 by The Inter Project Authors | PDF reports | SIL Open Font License 1.1 | `mtg_deck_tester/fonts/` (license in `OFL.txt`) |

The web interface uses your operating system's own font (San Francisco on macOS, Segoe UI on
Windows) and loads nothing from the internet. Apple's San Francisco and SF Symbols are not used in
or distributed with the PDF reports, as their license limits them to Apple platforms.

## Wizards of the Coast

MTG Commander Deck Tester is unofficial Fan Content permitted under the
[Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy). Not approved/endorsed by
Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.

Magic: The Gathering and all card names are trademarks of Wizards of the Coast LLC.
This project is not affiliated with Forge, Commander Spellbook, EDHREC, Archidekt, Moxfield, Scryfall, Inter or Anthropic.
