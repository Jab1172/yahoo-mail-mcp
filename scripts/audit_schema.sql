PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS audit_runs (
 id INTEGER PRIMARY KEY,
 started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 source TEXT NOT NULL,
 batch_size INTEGER NOT NULL DEFAULT 5000,
 status TEXT NOT NULL DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS messages (
 account TEXT NOT NULL,
 folder TEXT NOT NULL,
 uidvalidity INTEGER NOT NULL,
 uid INTEGER NOT NULL,
 message_id TEXT,
 sender TEXT,
 sender_domain TEXT,
 subject TEXT,
 sent_at TEXT,
 classification TEXT NOT NULL DEFAULT 'review',
 proposed_action TEXT NOT NULL DEFAULT 'keep_for_review',
 PRIMARY KEY (account, folder, uidvalidity, uid)
);
CREATE TABLE IF NOT EXISTS checkpoints (
 account TEXT NOT NULL,
 folder TEXT NOT NULL,
 uidvalidity INTEGER NOT NULL,
 last_uid INTEGER NOT NULL DEFAULT 0,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY (account, folder, uidvalidity)
);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender);
CREATE INDEX IF NOT EXISTS idx_messages_domain ON messages(sender_domain);
CREATE INDEX IF NOT EXISTS idx_messages_class ON messages(classification);
