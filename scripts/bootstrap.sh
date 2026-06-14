#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/bootstrap.sh [--browser] [--tts] [--asr] [--all] [--no-smoke]

Default setup is intentionally light: dev dependencies only, then doctor and
offline smoke run. Heavy model/audio dependencies are opt-in.

Options:
  --browser   Install Playwright extra and Chromium browser.
  --tts       Install TTS extra dependencies used by VibeVoice integration.
  --asr       Install Whisper ASR extra used by optional sample text leak checks.
  --all       Install browser, tts, and asr extras.
  --no-smoke  Skip the offline smoke run.

Environment:
  PYTHON                 Python executable to use. Default: python3
  WEB_TO_PODCAST_VENV    Virtualenv directory. Default: .venv
EOF
}

python_bin="${PYTHON:-python3}"
venv_dir="${WEB_TO_PODCAST_VENV:-.venv}"
install_browser=0
install_tts=0
install_asr=0
run_smoke=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --browser)
      install_browser=1
      ;;
    --tts)
      install_tts=1
      ;;
    --asr)
      install_asr=1
      ;;
    --all)
      install_browser=1
      install_tts=1
      install_asr=1
      ;;
    --no-smoke)
      run_smoke=0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

if [[ ! -d "$venv_dir" ]]; then
  "$python_bin" -m venv "$venv_dir"
fi

venv_python="$venv_dir/bin/python"
venv_cli="$venv_dir/bin/web-to-podcast"

"$venv_python" -m ensurepip --upgrade >/dev/null 2>&1 || true
"$venv_python" -m pip install --upgrade pip setuptools wheel

extras=(dev)
if [[ "$install_browser" == "1" ]]; then
  extras+=(browser)
fi
if [[ "$install_tts" == "1" ]]; then
  extras+=(tts)
fi
if [[ "$install_asr" == "1" ]]; then
  extras+=(asr)
fi

IFS=,
extra_spec="${extras[*]}"
unset IFS
"$venv_python" -m pip install -e ".[${extra_spec}]"

if [[ "$install_browser" == "1" ]]; then
  "$venv_python" -m playwright install chromium
fi

"$venv_cli" doctor

if [[ "$run_smoke" == "1" ]]; then
  rm -rf output/local-smoke
  "$venv_cli" run --config examples/local_markdown.json --force
  "$venv_cli" status --output-dir output/local-smoke
fi

cat <<EOF

Setup complete.
Activate the environment with:
  source "$venv_dir/bin/activate"
EOF
