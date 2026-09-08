#!/bin/sh
# Pin GitHub CLI (and HTTPS git via `gh auth git-credential`) to Alfareiza
# in this workspace only. Does not change the machine-wide active `gh` account.
#
# One-time setup: `gh auth login --hostname github.com` as Alfareiza
# (add it as a second account; alfonsorevin can stay the default elsewhere).

set -eu

token=""
if token=$(gh auth token --hostname github.com --user Alfareiza 2>/dev/null); then
  :
fi

if [ -z "${token}" ]; then
  printf '%s\n' '{"additional_context":"This repo is pinned to GitHub user Alfareiza. Add that account once with: gh auth login --hostname github.com. Keep another account as the default if you want; this workspace will still use Alfareiza after that login."}'
  exit 0
fi

git config --local credential.helper '!gh auth git-credential'
TOKEN="$token" python3 -c 'import json, os; print(json.dumps({"env": {"GH_TOKEN": os.environ["TOKEN"]}}))'
