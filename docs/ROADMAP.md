# Audit roadmap

1. Keep MCP tools in `READ_ONLY=true` mode. Verify available tools with MCP inspector.
2. Add a standalone read-only IMAP collector (or validated MCP pagination) using UID SEARCH/FETCH, never STORE, MOVE, EXPUNGE or DELETE.
3. Enumerate all selected folders, recording UIDVALIDITY and UID checkpoints; handle UIDVALIDITY changes by rescan.
4. Fetch metadata in chunks of at most 5,000 messages per batch, with smaller IMAP request windows and retries.
5. Persist idempotently to SQLite using composite folder/UIDVALIDITY/UID keys.
6. Produce CSV reports: messages, senders, domains, cleanup candidates, audit summary, duplicates.
7. Require human review of classifications; no mutation path in the audit worker.
8. Test with synthetic mbox/IMAP fixtures and compare per-folder counts against Yahoo/Thunderbird.

Privacy: keep reports local, do not commit them, and redact sensitive fields before sharing.
