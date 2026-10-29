#!/usr/bin/env python3
"""Local metadata audit. IMAP reads only; Python 3.10+, standard library only."""
import argparse
import csv
import email.policy
import imaplib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from email.parser import BytesHeaderParser
from email.utils import parseaddr

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_messages (
 account TEXT, folder TEXT, uidvalidity INTEGER, uid INTEGER,
 message_id TEXT, sender TEXT, domain TEXT, subject TEXT, sent_at TEXT,
 seen INTEGER, newsletter INTEGER,
 PRIMARY KEY(account,folder,uidvalidity,uid));
CREATE TABLE IF NOT EXISTS audit_state (
 account TEXT, folder TEXT, uidvalidity INTEGER, last_uid INTEGER,
 PRIMARY KEY(account,folder));
CREATE INDEX IF NOT EXISTS audit_sender ON audit_messages(account,sender);
"""
FETCH = '(UID FLAGS BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM SUBJECT DATE LIST-UNSUBSCRIBE LIST-ID)])'


def database(path):
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    os.chmod(path, 0o600)
    return db


def ok(result, operation):
    status, data = result
    if status != 'OK':
        raise RuntimeError(f'{operation} failed; checkpoint not advanced')
    return data


def collect(client, db, account, folder, batch_size=5000, window=100, max_batches=None):
    """Snapshot UIDs; commit complete batches. Failures replay the unfinished batch."""
    if not 1 <= batch_size <= 5000 or not 1 <= window <= 100:
        raise ValueError('batch_size must be 1..5000; window must be 1..100')
    # Quote folder names so spaces and IMAP metacharacters remain mailbox data.
    mailbox = '"' + folder.replace('\\', '\\\\').replace('"', '\\"') + '"'
    ok(client.select(mailbox, readonly=True), 'EXAMINE')
    _, validity = client.response('UIDVALIDITY')
    if not validity or not validity[0] or not validity[0].isdigit():
        raise RuntimeError('Missing UIDVALIDITY')
    epoch = int(validity[0])
    state = db.execute('SELECT uidvalidity,last_uid FROM audit_state WHERE account=? AND folder=?',
                       (account, folder)).fetchone()
    last = state[1] if state and state[0] == epoch else 0
    found = ok(client.uid('SEARCH', None, 'ALL'), 'UID SEARCH')
    uids = sorted({int(uid) for part in found if part for uid in part.split() if int(uid) > last})
    batches = 0
    processed = 0
    # Drop stale epoch rows even when the new mailbox is empty.
    with db:
        db.execute('DELETE FROM audit_messages WHERE account=? AND folder=? AND uidvalidity!=?',
                   (account, folder, epoch))
        db.execute('INSERT OR REPLACE INTO audit_state VALUES (?,?,?,?)', (account, folder, epoch, last))
    for offset in range(0, len(uids), batch_size):
        if max_batches is not None and batches >= max_batches:
            break
        batch = uids[offset:offset + batch_size]
        with db:
            for start in range(0, len(batch), window):
                requested = batch[start:start + window]
                rows = ok(client.uid('FETCH', ','.join(map(str, requested)), FETCH), 'UID FETCH')
                received = set()
                for item in rows:
                    if not isinstance(item, tuple):
                        continue
                    meta, raw = item
                    uid_match = re.search(rb'\bUID (\d+)\b', meta)
                    if not uid_match:
                        raise RuntimeError('FETCH omitted UID')
                    uid = int(uid_match[1])
                    if uid not in requested or uid in received:
                        raise RuntimeError('Unexpected or duplicate FETCH UID')
                    received.add(uid)
                    msg = BytesHeaderParser(policy=email.policy.default).parsebytes(raw)
                    sender = parseaddr(str(msg.get('From', '')))[1].lower()
                    flags = re.search(rb'FLAGS \(([^)]*)\)', meta)
                    if not flags:
                        raise RuntimeError('FETCH omitted FLAGS')
                    db.execute('INSERT OR REPLACE INTO audit_messages VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                               (account, folder, epoch, uid, str(msg.get('Message-ID', '')), sender,
                                sender.rpartition('@')[2], str(msg.get('Subject', '')),
                                str(msg.get('Date', '')), int(b'\\Seen' in flags[1].split()),
                                int(bool(msg.get('List-Unsubscribe') or msg.get('List-ID')))))
                # Do not silently skip expunged/incomplete results; retry on next run.
                if received != set(requested):
                    raise RuntimeError('Incomplete FETCH; rerun to refresh the UID snapshot')
            db.execute('INSERT OR REPLACE INTO audit_state VALUES (?,?,?,?)',
                       (account, folder, epoch, batch[-1]))
        processed += len(batch)
        batches += 1
        print(json.dumps({'folder': folder, 'batch': batches, 'processed': processed,
                          'last_uid': batch[-1]}), file=sys.stderr)
    return processed


def safe_cell(value):
    # Prevent spreadsheet formula execution from untrusted email headers.
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def reports(db, account, directory):
    directory = Path(directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    queries = {
        'messages': 'SELECT * FROM audit_messages WHERE account=? ORDER BY folder,uid',
        'senders': '''SELECT sender,COUNT(*) AS messages,SUM(seen) AS currently_seen,
                     SUM(newsletter) AS newsletter_messages FROM audit_messages
                     WHERE account=? GROUP BY sender ORDER BY messages DESC,sender''',
        'domains': '''SELECT domain,COUNT(*) AS messages FROM audit_messages
                     WHERE account=? GROUP BY domain ORDER BY messages DESC,domain''',
        'cleanup_candidates': '''SELECT folder,uidvalidity,uid,sender,subject,
                     'newsletter_header_present; human_review_required' AS reason
                     FROM audit_messages WHERE account=? AND newsletter=1 ORDER BY folder,uid''',
        'duplicates': '''SELECT message_id,COUNT(*) AS copies FROM audit_messages
                     WHERE account=? AND message_id!='' GROUP BY message_id HAVING COUNT(*)>1''',
        'summary': '''SELECT folder,uidvalidity,COUNT(*) AS indexed_messages FROM audit_messages
                     WHERE account=? GROUP BY folder,uidvalidity''',
    }
    for name, query in queries.items():
        cursor = db.execute(query, (account,))
        target = directory / (name + '.csv')
        with target.open('w', newline='', encoding='utf-8') as stream:
            os.chmod(target, 0o600)
            writer = csv.writer(stream)
            writer.writerow([column[0] for column in cursor.description])
            writer.writerows([safe_cell(value) for value in row] for row in cursor)


def password(account):
    if sys.platform != 'darwin':
        raise RuntimeError('Live audit requires macOS Keychain')
    result = subprocess.run(['security', 'find-generic-password', '-a', account,
                             '-s', 'yahoo-mail-mcp', '-w'], capture_output=True, text=True, timeout=30)
    if result.returncode or not result.stdout.strip():
        raise RuntimeError('Yahoo app password unavailable in Keychain; run setup-macos.sh')
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account', required=True)
    parser.add_argument('--folder', action='append', help='Repeat for each folder; default: INBOX')
    parser.add_argument('--db', default='data/audit.sqlite3')
    parser.add_argument('--reports', default='reports')
    parser.add_argument('--batch-size', type=int, default=5000)
    parser.add_argument('--max-batches', type=int, help='Limit batches per folder for a first test')
    parser.add_argument('--reports-only', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 5000 or (args.max_batches is not None and args.max_batches < 1):
        parser.error('batch size must be 1..5000 and max batches positive')
    os.umask(0o077)
    with database(args.db) as db:
        if not args.reports_only:
            client = imaplib.IMAP4_SSL('imap.mail.yahoo.com', 993, timeout=60)
            try:
                ok(client.login(args.account, password(args.account)), 'LOGIN')
                for folder in args.folder or ['INBOX']:
                    collect(client, db, args.account, folder, args.batch_size, max_batches=args.max_batches)
            finally:
                # No CLOSE: LOGOUT directly from read-only mailbox.
                client.logout()
        reports(db, args.account, args.reports)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, imaplib.IMAP4.error, OSError, subprocess.TimeoutExpired) as exc:
        print(f'Audit stopped ({type(exc).__name__}); committed batches can be resumed.', file=sys.stderr)
        sys.exit(1)
