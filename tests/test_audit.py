import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('audit', Path(__file__).parents[1] / 'scripts/audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

class FakeIMAP:
    def __init__(self, count=5001, epoch=1, fail_uid=None, omit=False):
        self.count, self.epoch, self.fail_uid, self.omit = count, epoch, fail_uid, omit
        self.calls = []
    def select(self, folder, readonly=False):
        assert readonly is True
        self.calls.append(('EXAMINE', folder))
        return 'OK', [str(self.count).encode()]
    def response(self, name):
        assert name == 'UIDVALIDITY'
        return name, [str(self.epoch).encode()]
    def uid(self, command, *args):
        self.calls.append((command, args))
        if command == 'SEARCH':
            return 'OK', [' '.join(map(str, range(1, self.count + 1))).encode()]
        assert command == 'FETCH'
        assert 'BODY.PEEK[' in args[1]
        ids = list(map(int, args[0].split(',')))
        assert len(ids) <= 100
        if self.fail_uid in ids:
            return 'NO', [b'failure']
        return 'OK', [(f'{uid} (UID {uid} FLAGS ())'.encode(),
            f'From: Person <person@example.com>\r\nSubject: =bad()\r\nMessage-ID: <{uid}>\r\nList-ID: news\r\n\r\n'.encode())
            for uid in (ids[:-1] if self.omit else ids)]

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = audit.database(Path(self.tmp.name) / 'audit.sqlite3')
    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()
    def test_5000_batch_resume_and_epoch_reset(self):
        fake = FakeIMAP()
        self.assertEqual(audit.collect(fake, self.db, 'test', 'INBOX', max_batches=1), 5000)
        self.assertEqual(audit.collect(fake, self.db, 'test', 'INBOX'), 1)
        self.assertEqual(audit.collect(fake, self.db, 'test', 'INBOX'), 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM audit_messages').fetchone()[0], 5001)
        audit.collect(FakeIMAP(count=2, epoch=2), self.db, 'test', 'INBOX')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM audit_messages').fetchone()[0], 2)
    def test_failure_rolls_back_batch(self):
        with self.assertRaises(RuntimeError):
            audit.collect(FakeIMAP(count=201, fail_uid=150), self.db, 'test', 'INBOX')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM audit_messages').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT last_uid FROM audit_state').fetchone()[0], 0)
    def test_missing_fetch_does_not_skip_uid(self):
        with self.assertRaises(RuntimeError):
            audit.collect(FakeIMAP(count=2, omit=True), self.db, 'test', 'INBOX')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM audit_messages').fetchone()[0], 0)
    def test_reports_and_account_isolation(self):
        audit.collect(FakeIMAP(count=2), self.db, 'test', 'INBOX')
        audit.collect(FakeIMAP(count=1), self.db, 'other', 'INBOX')
        directory = Path(self.tmp.name) / 'reports'
        audit.reports(self.db, 'test', directory)
        self.assertEqual(len(list(directory.glob('*.csv'))), 6)
        self.assertIn("'=bad()", (directory / 'messages.csv').read_text())
        self.assertIn('person@example.com,2,0,2', (directory / 'senders.csv').read_text())
    def test_quoted_folder(self):
        fake = FakeIMAP(count=0)
        audit.collect(fake, self.db, 'test', 'My Folder')
        self.assertEqual(fake.calls[0], ('EXAMINE', '"My Folder"'))

if __name__ == '__main__':
    unittest.main()
