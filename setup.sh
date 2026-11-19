#!/bin/zsh
# Обёртка для установки из zip или клона: настоящий скрипт лежит внутри скилла монтажа.
#   zsh setup.sh        — Claude Code
#   zsh setup.sh codex  — Codex
exec zsh "${0:A:h}/skills/short-video-editing/setup/setup.sh" "${1:-claude}"
