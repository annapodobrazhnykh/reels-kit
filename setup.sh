#!/bin/zsh
# Установка набора для рилсов: программы, модель распознавания речи, папка проекта, скиллы.
# Запуск из папки набора (распакованный zip или клон репозитория):
#   zsh setup.sh          — программы + скиллы для Claude Code (~/.claude/skills)
#   zsh setup.sh codex    — программы + скиллы для Codex (~/.agents/skills)
#   zsh setup.sh tools    — только программы (если скиллы уже поставлены через `npx skills add`)
# Рабочая папка для роликов у всех одна: ~/Desktop/shortVideos
# Повторный запуск безопасен.
set -e
KIT="${0:A:h}"
AGENT="${1:-claude}"

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
brew install ffmpeg-full whisper-cpp yt-dlp gh python@3.12

echo "→ Папка проекта $ROOT"
mkdir -p "$ROOT"/{videos,_published,_covers,_system/tools,_system/sfx,_strategy/{creators,trends,ideas}}
cp -n "$KIT"/sfx/*.wav "$ROOT/_system/sfx/" 2>/dev/null || true
[[ -f "$ROOT/_system/brand.md" ]] || cp "$KIT/brand.md" "$ROOT/_system/brand.md"
[[ -f "$ROOT/_system/broll-library.md" ]] || printf '# Библиотека вставок\n\n| файл | что на нём | где использовано |\n|---|---|---|\n' > "$ROOT/_system/broll-library.md"
[[ -f "$ROOT/AGENTS.md" ]] || cp "$KIT/AGENTS.md" "$ROOT/AGENTS.md"

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
  for s in "$KIT"/skills/*; do
    name="${s:t}"
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
