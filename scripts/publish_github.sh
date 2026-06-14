#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/publish_github.sh [remote-url]
  scripts/publish_github.sh --gh <owner-or-owner/repo> [--public|--private]

Examples:
  scripts/publish_github.sh git@github.com:you/web-to-podcast.git
  scripts/publish_github.sh --gh you/web-to-podcast --private
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "error: run this from the web-to-podcast git repository" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "error: working tree is not clean; commit or stash changes first" >&2
  exit 1
fi

branch="$(git branch --show-current)"
if [[ -z "$branch" ]]; then
  echo "error: could not determine current branch" >&2
  exit 1
fi

if [[ "${1:-}" == "--gh" ]]; then
  repo="${2:-}"
  visibility="${3:---private}"
  if [[ -z "$repo" ]]; then
    echo "error: missing owner/repo after --gh" >&2
    usage
    exit 1
  fi
  if ! command -v gh >/dev/null 2>&1; then
    echo "error: gh CLI is not installed or not on PATH" >&2
    exit 1
  fi
  gh repo create "$repo" "$visibility" --source=. --remote=origin --push
  exit 0
fi

remote_url="${1:-}"
if [[ -n "$remote_url" ]]; then
  if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "$remote_url"
  else
    git remote add origin "$remote_url"
  fi
elif ! git remote get-url origin >/dev/null 2>&1; then
  echo "error: no origin remote configured and no remote-url provided" >&2
  usage
  exit 1
fi

git push -u origin "$branch"
