# Personal Yahoo audit (macOS)

This fork preserves upstream's Node MCP server and adds a standard-library Python
3.10+ metadata audit. No credentials, mailbox data, reports or databases belong in Git.
The upstream README remains the guide for the MCP client and Node installation.

## Configure locally

Install upstream dependencies with `npm ci`. Run `bash scripts/setup-macos.sh` to
store your Yahoo app password in macOS Keychain and create a local `.env` with
`READ_ONLY=true`. Run `bash scripts/check-safety.sh` before launching the MCP server.
The Python worker reads Keychain directly; it does not source `.env` or execute a
password command from configuration. Do not paste your app password into a chat.

## First audit

```bash
python3 -m unittest discover -s tests -v
python3 scripts/audit.py --account you@yahoo.com --max-batches 1
```

This audits at most 5,000 messages in INBOX and writes `data/audit.sqlite3` plus
six CSV reports under `reports/`. Run the same command without `--max-batches`
to resume and process the remaining UIDs. Use repeated `--folder` options for
additional folders, using the exact IMAP names shown by upstream's `list_folders`:

```bash
python3 scripts/audit.py --account you@yahoo.com --folder INBOX --folder Archive
python3 scripts/audit.py --account you@yahoo.com --reports-only
```

Folders are explicit; the default does **not** cover your entire account. Compare
indexed counts with each selected mailbox before calling the initial audit complete.
The database and reports contain sensitive header metadata; keep them local.

## Guarantees and limits

- EXAMINE/read-only selection, UID SEARCH, and UID FETCH with BODY.PEEK headers;
  no bodies, attachments, STORE, MOVE, DELETE, EXPUNGE, or CLOSE commands.
- Up to 5,000 messages per transaction; at most 100 UIDs per FETCH request.
- A failed or incomplete batch rolls back. Rerun to retry with a fresh UID snapshot.
- Keys include account, folder, UIDVALIDITY, and UID. A changed UIDVALIDITY replaces
  that folder's old index. Committed batches are idempotent across restarts.
- This is an incremental header index. Existing UIDs are not refreshed on resume;
  read flags can become stale and subsequently removed messages stay indexed.
  For a fresh snapshot, choose a new `--db` path and a new `--reports` directory.
- Sender/domain reports count indexed copies across selected folders. Repeated
  Message-ID values are duplicate *candidates*, not proof of duplicate content.
- Newsletter candidates require List-ID or List-Unsubscribe. They are review
  suggestions, not spam verdicts. No message is deleted or modified.
- Current Seen flags cannot prove whether you interacted with a newsletter over
  two years. Historical engagement is unavailable from this metadata alone.
- CSV cells escape formula-like header values before opening in spreadsheets.

## Next integration milestone

The CSV sender report already ranks frequent senders. The Node MCP server does
not yet query this SQLite index. Add bounded, account-scoped read-only MCP queries
for top senders and newsletter candidates after validating a live audit locally.
Do not expose arbitrary SQL, credentials, or unbounded email contents to the model.
Live Yahoo and macOS Keychain behavior still require testing on your Mac.

## Offline validation

`python3 -m unittest discover -s tests -v` covers batch boundaries, restart,
UIDVALIDITY changes, rollback, incomplete FETCH responses, quoted folders,
account isolation and safe CSV output. `npm test` runs upstream Node tests.

`scripts/audit_schema.sql` is retained from the original overlay as design history;
the worker owns its separate `audit_messages`/`audit_state` schema.
