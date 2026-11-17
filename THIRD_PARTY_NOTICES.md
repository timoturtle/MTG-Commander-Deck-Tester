# Third-party software, services and notices

MTG Commander Deck Tester's own code is released under the [MIT License](LICENSE).
It does **not** bundle any third-party code, fonts or card data. The items below are
installed separately, downloaded by the user, or contacted over the internet while the app runs.

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
modify Forge's code. To record opening hands, the small helper `mtg_deck_tester/java/HandSim.java`
(part of this project, MIT-licensed, which is compatible with the GPL) is compiled on your own
computer against your own copy of Forge and runs together with it there; no compiled combination
of the two is distributed. Forge's license applies to Forge itself.

## Online services

| Service | Used for | Notes |
|---|---|---|
| [Scryfall API](https://scryfall.com/docs/api) | Card names, colour identity, card types | Used per Scryfall's API guidelines (identifying User-Agent, rate limits, local caching). Card data is © Wizards of the Coast. |
| [Archidekt](https://archidekt.com) | Finding popular public decks | Public but undocumented API, used at a low request rate. Deck lists belong to their authors. |
| [Moxfield](https://moxfield.com) | Finding popular public decks (optional) | Off by default. Moxfield's terms don't allow automated access without permission; the feature only runs with a User-Agent that Moxfield issued to you (ask support@moxfield.com). |
| [Claude API](https://www.anthropic.com/api) by Anthropic | Optional coaching notes | Only with your own API key; usage is billed to your account and subject to Anthropic's terms. |

## Fonts

- The web interface loads **Barlow Condensed** and **Atkinson Hyperlegible** from Google Fonts
  (SIL Open Font License 1.1). They are not stored in this repository; without internet the
  interface falls back to system fonts.
- PDF reports use fonts that are already installed with your operating system (Arial or Segoe UI;
  DejaVu Sans on Linux) or the built-in PDF font Helvetica. No font files are distributed.

## Wizards of the Coast

MTG Commander Deck Tester is unofficial Fan Content permitted under the
[Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy). Not approved/endorsed by
Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.

Magic: The Gathering and all card names are trademarks of Wizards of the Coast LLC.
This project is not affiliated with Forge, Archidekt, Moxfield, Scryfall or Anthropic.
