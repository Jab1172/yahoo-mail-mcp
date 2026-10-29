#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != "Darwin" ]]; then echo 'macOS required' >&2; exit 1; fi
if [[ -e .env ]]; then echo '.env already exists; refusing to overwrite' >&2; exit 1; fi
umask 077
read -r -p 'Yahoo email address: ' yahoo_email
if [[ ! "$yahoo_email" =~ ^[a-zA-Z0-9._+%-]+@[a-zA-Z0-9.-]+$ ]]; then echo 'Invalid email' >&2; exit 1; fi
printf 'Paste your Yahoo app password when prompted by macOS Keychain (hidden).\n'
security add-generic-password -a "$yahoo_email" -s yahoo-mail-mcp -T '' -w
cat > .env <<CONFIG
YAHOO_EMAIL=$yahoo_email
YAHOO_APP_PASSWORD_COMMAND=security find-generic-password -a $yahoo_email -s yahoo-mail-mcp -w
READ_ONLY=true
CONFIG
chmod 600 .env
printf 'Created .env (mode 600). Review upstream README for variable compatibility.\n'
