import json, sqlite3, time
from pathlib import Path
from . import config

SCHEMA = '''
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, status TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL, error TEXT);
CREATE TABLE IF NOT EXISTS clips(id TEXT PRIMARY KEY, data TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, data TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
'''
def connect():
    db=sqlite3.connect(config.DB_PATH, timeout=30)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    return db

def init_db():
    with connect() as db: db.executescript(SCHEMA)

def create_job(job_id, payload):
    now=time.time()
    with connect() as db: db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,NULL)',(job_id,'pending',json.dumps(payload),now,now))

def update_job(job_id,status,error=None):
    with connect() as db: db.execute('UPDATE jobs SET status=?,updated_at=?,error=? WHERE id=?',(status,time.time(),error,job_id))

def list_jobs():
    with connect() as db: rows=db.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100').fetchall()
    return [dict(r) | {'payload':json.loads(r['payload'])} for r in rows]

def save_clip(clip):
    with connect() as db: db.execute('INSERT OR REPLACE INTO clips VALUES(?,?,?)',(clip['id'],json.dumps(clip),clip['created_at']))

def list_clips():
    with connect() as db: rows=db.execute('SELECT data FROM clips ORDER BY created_at DESC LIMIT 500').fetchall()
    return [json.loads(r['data']) for r in rows]

def add_event(kind,data):
    with connect() as db: db.execute('INSERT INTO events(kind,data,created_at) VALUES(?,?,?)',(kind,json.dumps(data),time.time()))

def list_events():
    with connect() as db: rows=db.execute('SELECT kind,data,created_at FROM events ORDER BY id DESC LIMIT 100').fetchall()
    return [{'type':r['kind'],'data':json.loads(r['data']),'created_at':r['created_at']} for r in rows]
