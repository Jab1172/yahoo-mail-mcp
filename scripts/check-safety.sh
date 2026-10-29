#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -f .env ]] || { echo 'Missing .env' >&2; exit 1; }
grep -Eq '^READ_ONLY=true$' .env || { echo 'READ_ONLY=true is required' >&2; exit 1; }
if grep -Eq '^YAHOO_APP_PASSWORD=' .env; then echo 'Plaintext password variable forbidden' >&2; exit 1; fi
if ! grep -Eq '^YAHOO_APP_PASSWORD_COMMAND=' .env; then echo 'Missing password command' >&2; exit 1; fi
printf 'Local configuration safety checks passed. This does not prove runtime IMAP read-only behavior.\n'
