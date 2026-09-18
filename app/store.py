from contextlib import contextmanager
import json
import sqlite3


class Store:
    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "wiki.sqlite3"

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def initialize(self):
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, fingerprint TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id)
                    ON DELETE CASCADE, heading TEXT NOT NULL, text TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS wiki_pages (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    request_id TEXT PRIMARY KEY REFERENCES requests(id), solved INTEGER NOT NULL,
                    reason TEXT NOT NULL, updated_at TEXT NOT NULL
                );
            """)

    def documents(self):
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM documents ORDER BY id")]

    def wiki_pages(self):
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM wiki_pages ORDER BY id")]

    def state(self):
        with self.connection() as db:
            return {row[0]: json.loads(row[1]) for row in db.execute("SELECT key,value FROM state")}

    def set_state(self, key, value):
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO state VALUES (?, ?)", (key, json.dumps(value)))

    def save_request(self, payload):
        with self.connection() as db:
            db.execute("INSERT INTO requests VALUES (?, ?, ?)",
                       (payload["request_id"], json.dumps(payload, ensure_ascii=False), payload["created_at"]))

    def feedback(self, request_id, solved, reason, now):
        with self.connection() as db:
            if not db.execute("SELECT 1 FROM requests WHERE id=?", (request_id,)).fetchone():
                return False
            db.execute("INSERT INTO feedback VALUES (?,?,?,?) ON CONFLICT(request_id) DO UPDATE SET "
                       "solved=excluded.solved,reason=excluded.reason,updated_at=excluded.updated_at",
                       (request_id, solved, reason, now))
            return True
