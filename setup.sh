#!/bin/zsh
# Wrapper for installing from the zip or a clone: the real script lives inside the editing skill.
#   zsh setup.sh        — Claude Code
#   zsh setup.sh codex  — Codex
exec zsh "${0:A:h}/skills/short-video-editing/setup/setup.sh" "${1:-claude}"
