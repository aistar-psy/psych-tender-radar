"""SQLite history: preserve notice versions, and explicit unresolved work."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from .fetch import canonical_url

def stamp(): return datetime.now(timezone.utc).isoformat()
def key(value): return hashlib.sha256(value.encode()).hexdigest()[:24]

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, data TEXT, first_seen TEXT, last_seen TEXT);
        CREATE TABLE IF NOT EXISTS notices(url TEXT PRIMARY KEY, project_id TEXT, latest_hash TEXT, first_seen TEXT, last_seen TEXT);
        CREATE TABLE IF NOT EXISTS versions(url TEXT, hash TEXT, project_id TEXT, data TEXT, run_id TEXT, fetched_at TEXT, PRIMARY KEY(url,hash));
        CREATE TABLE IF NOT EXISTS backlog(id TEXT PRIMARY KEY, kind TEXT, error TEXT, attempts INTEGER, status TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, data TEXT);
        ''')
    def save_document(self,url,data,digest,run_id):
        url=canonical_url(url);now=stamp()
        old=self.db.execute('SELECT project_id FROM notices WHERE url=?',(url,)).fetchone()
        # Never merge two institutions merely because they reuse a local project number.
        number=data.get('project_number')
        buyer=data.get('buyer') or urlsplit(url).netloc
        pid=old['project_id'] if old else key(f'{buyer}|{number}' if number else url)
        self.db.execute('INSERT INTO projects VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,last_seen=excluded.last_seen',
                        (pid,json.dumps(data,ensure_ascii=False),now,now))
        self.db.execute('INSERT INTO notices VALUES(?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET latest_hash=excluded.latest_hash,last_seen=excluded.last_seen',
                        (url,pid,digest,now,now))
        self.db.execute('INSERT OR IGNORE INTO versions VALUES(?,?,?,?,?,?)',
                        (url,digest,pid,json.dumps(data,ensure_ascii=False),run_id,now))
        self.db.commit();return pid
    def backlog(self, identifier, kind, error):
        self.db.execute('INSERT INTO backlog VALUES(?,?,?,1,?,?) ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,error=excluded.error,attempts=backlog.attempts+1,status=excluded.status,updated_at=excluded.updated_at',
                        (identifier,kind,str(error),'pending',stamp()))
        self.db.commit()
    def resolve(self,identifier):
        self.db.execute("UPDATE backlog SET status='resolved',updated_at=? WHERE id=?",(stamp(),identifier));self.db.commit()
    def pending(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM backlog WHERE status='pending' ORDER BY updated_at")]
    def counts(self):
        return {name:self.db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ('projects','notices','versions')}
    def get(self,name,default=None):
        row=self.db.execute('SELECT value FROM settings WHERE key=?',(name,)).fetchone()
        return json.loads(row['value']) if row else default
    def set(self,name,value):
        self.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(name,json.dumps(value)));self.db.commit()
    def save_run(self,run_id,value):
        self.db.execute('INSERT OR REPLACE INTO runs VALUES(?,?)',(run_id,json.dumps(value,ensure_ascii=False)));self.db.commit()
    def known_urls(self):
        return [r['url'] for r in self.db.execute('SELECT url FROM notices ORDER BY last_seen')]
    def close(self): self.db.close()
