#!/bin/bash
# Try MTG Commander Deck Tester with fake games (no Java or Forge needed).
cd "$(dirname "$0")" || exit 1
exec bash ./start-mac.command --demo
