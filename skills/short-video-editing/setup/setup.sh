#!/bin/zsh
# Установка набора для рилсов: программы, модель распознавания речи, папка проекта, скиллы.
# Скрипт лежит внутри скилла short-video-editing/setup/. Режимы:
#   zsh setup.sh          — если скиллы уже стоят (npx skills add или установлены раньше): только программы;
#                           если запущен из распакованного zip / клона: программы + скиллы для Claude Code
#   zsh setup.sh codex    — программы + скиллы для Codex (~/.agents/skills)
#   zsh setup.sh claude   — программы + скиллы для Claude Code (~/.claude/skills)
#   zsh setup.sh tools    — только программы
# Рабочая папка для роликов у всех одна: ~/Desktop/shortVideos
# Повторный запуск безопасен.
set -e
SETUP="${0:A:h}"          # .../short-video-editing/setup
EDIT="${SETUP:h}"          # .../short-video-editing
SRC="${EDIT:h}"            # папка со всеми скиллами набора
KIT_SKILLS=(short-video-strategy short-video-editing reel-covers short-video-publishing)
if [[ -n "$1" ]]; then
  AGENT="$1"
elif [[ "$SRC" == */.claude/skills || "$SRC" == */.agents/skills ]]; then   # уже стоят у агента (глобально или в проекте)
  AGENT=tools
else
  AGENT=claude
fi

ROOT="$HOME/Desktop/shortVideos"
case "$AGENT" in
  claude) SKILLS="$HOME/.claude/skills" ;;
  codex)  SKILLS="$HOME/.agents/skills" ;;
  tools)  SKILLS="" ;;
  *) echo "Неизвестный режим «$AGENT». Используй: zsh setup.sh  |  zsh setup.sh codex  |  zsh setup.sh tools"; exit 1 ;;
esac

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "Нужен Mac на Apple Silicon (M1/M2/M3/M4): скиллы рассчитаны на /opt/homebrew."; exit 1
fi

if [[ ! -x /opt/homebrew/bin/brew ]]; then
  echo "→ Ставлю Homebrew (попросит пароль от Mac)"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
eval "$(/opt/homebrew/bin/brew shellenv)"
grep -q 'brew shellenv' ~/.zprofile 2>/dev/null || echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile

echo "→ Программы: ffmpeg-full, whisper.cpp, yt-dlp, gh, python"
PKGS=(ffmpeg-full whisper-cpp yt-dlp python@3.12)
command -v gh >/dev/null || PKGS+=(gh)   # gh мог стоять не через brew — не дублируем
brew install $PKGS

echo "→ Папка проекта $ROOT"
mkdir -p "$ROOT"/{videos,_published,_covers,_system/tools,_system/sfx,_strategy/{creators,trends,ideas}}
cp -n "$EDIT"/assets/*.wav "$ROOT/_system/sfx/" 2>/dev/null || true
[[ -f "$ROOT/_system/brand.md" ]] || cp "$SETUP/brand.md" "$ROOT/_system/brand.md"
[[ -f "$ROOT/_system/broll-library.md" ]] || printf '# Библиотека вставок\n\n| файл | что на нём | где использовано |\n|---|---|---|\n' > "$ROOT/_system/broll-library.md"
[[ -f "$ROOT/AGENTS.md" ]] || cp "$SETUP/AGENTS.md" "$ROOT/AGENTS.md"
[[ -f "$ROOT/CLAUDE.md" ]] || cp "$SETUP/AGENTS.md" "$ROOT/CLAUDE.md"   # то же для Claude Code

MODEL="$ROOT/_system/tools/ggml-large-v3-turbo.bin"
if [[ ! -s "$MODEL" ]]; then
  echo "→ Качаю модель Whisper (~1,6 ГБ, несколько минут)"
  curl -L --fail -o "$MODEL.part" https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin
  mv "$MODEL.part" "$MODEL"
fi

VENV="$ROOT/_system/tools/venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "→ Python-окружение"
  "$(brew --prefix python@3.12)/bin/python3.12" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q numpy scipy opencv-python Pillow pymupdf

if [[ -n "$SKILLS" ]]; then
  echo "→ Скиллы в $SKILLS"
  mkdir -p "$SKILLS"
  for name in $KIT_SKILLS; do
    s="$SRC/$name"
    if [[ -d "$SKILLS/$name" ]]; then
      echo "   $name уже есть — пропускаю (удали папку, если хочешь поставить заново)"
    else
      cp -R "$s" "$SKILLS/"
      echo "   $name ✓"
    fi
  done
fi

echo
echo "Проверка:"
/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg -hide_banner -filters 2>/dev/null | grep -q ' subtitles ' && echo "  ffmpeg с субтитрами ✓"
[[ -x /opt/homebrew/bin/whisper-cli ]] && echo "  whisper-cli ✓"
[[ -s "$MODEL" ]] && echo "  модель Whisper ✓"
"$VENV/bin/python" -c "import numpy, scipy, cv2, PIL, fitz" && echo "  python-библиотеки ✓"
echo
echo "Готово. Вернись к агенту (Claude / Codex) и напиши «готово»."
