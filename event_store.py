"""SQLite append-only-through-API inbox; not tamper-proof against DB administrators."""
import json
import sqlite3


class EventStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS inbox (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS attempts (seq INTEGER PRIMARY KEY, id TEXT, status TEXT NOT NULL, payload TEXT NOT NULL)')
        self.db.commit()

    def ingest(self, event):
        if not isinstance(event.get('id'), str) or not event['id']:
            raise ValueError('non-empty event ID required')
        payload = json.dumps(event, sort_keys=True, allow_nan=False, separators=(',', ':'))
        with self.db:
            # Obtain the write lock before checking, making concurrent retries atomic.
            self.db.execute('BEGIN IMMEDIATE')
            previous = self.db.execute('SELECT payload FROM inbox WHERE id=?', (event['id'],)).fetchone()
            status = 'accepted' if previous is None else 'duplicate' if previous[0] == payload else 'conflict'
            if previous is None:
                self.db.execute('INSERT INTO inbox VALUES (?, ?)', (event['id'], payload))
            self.db.execute('INSERT INTO attempts(id,status,payload) VALUES(?,?,?)', (event['id'],status,payload))
        return status

    def events(self):
        # Conflicting IDs are represented by all versions so reconciliation blocks them.
        return [json.loads(row[0]) for row in self.db.execute('SELECT payload FROM attempts ORDER BY seq')]

    def close(self):
        self.db.close()
