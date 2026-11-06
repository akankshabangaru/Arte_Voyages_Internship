"""Turso/sqlite storage. Local: sqlite3 via file: URL. Cloud: libsql-client via libsql:// URL."""
import os
import sqlite3
from datetime import date, datetime

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY, type TEXT NOT NULL, country TEXT, lat REAL, lon REAL,
        event_date TEXT NOT NULL, severity REAL NOT NULL, title TEXT NOT NULL,
        source_url TEXT, first_seen TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS trip_scores (
        trip_id TEXT NOT NULL, leg_id TEXT NOT NULL, place TEXT, country TEXT,
        lat REAL, lon REAL, start_date TEXT, end_date TEXT, score REAL, tier TEXT,
        driver TEXT, updated_at TEXT, PRIMARY KEY (trip_id, leg_id)
    )""",
    """CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id TEXT, leg_id TEXT,
        kind TEXT, tier TEXT, prev_tier TEXT, text TEXT NOT NULL, created_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS feed_health (
        feed TEXT PRIMARY KEY, last_ok TEXT, last_error TEXT, updated_at TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date)",
    "CREATE INDEX IF NOT EXISTS idx_scores_tier ON trip_scores(tier)",
    "CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at)",
]


def _url() -> str:
    return os.environ.get("TURSO_DATABASE_URL", "file:events.db")


_MEMORY_CON = None


def _close(con):
    if _url() == "file::memory:":
        return
    try:
        con.close()
    except Exception:
        pass

def _connect():
    global _MEMORY_CON
    url = _url()
    if url.startswith("libsql://"):
        try:
            import libsql_client  # type: ignore
        except ImportError:
            try:
                import libsql as libsql_client  # type: ignore
            except ImportError as e:
                raise RuntimeError("libsql-client is required for Turso cloud (pip install libsql-client)") from e
        token = os.environ.get("TURSO_AUTH_TOKEN", "")
        # libsql-client sync API
        return libsql_client.client(url=url, auth_token=token) if token else libsql_client.client(url=url)
    # file: URLs -> sqlite3
    if url == "file::memory:":
        if _MEMORY_CON is None:
            _MEMORY_CON = sqlite3.connect(":memory:")
        return _MEMORY_CON
    path = url[5:] if url.startswith("file:") else url
    return sqlite3.connect(path)


def init_db():
    con = _connect()
    try:
        for stmt in SCHEMA:
            try:
                con.execute(stmt)
            except AttributeError:
                # libsql-client executes via .execute too; tolerate both sync/async shapes
                import asyncio
                try:
                    asyncio.run(con.execute(stmt))
                except RuntimeError:
                    pass
        try:
            con.commit()
        except AttributeError:
            pass
    finally:
        try:
            _close(con)
        except AttributeError:
            pass


def upsert_event(ev, first_seen: datetime):
    con = _connect()
    try:
        con.execute(
            "INSERT INTO events (id,type,country,lat,lon,event_date,severity,title,source_url,first_seen) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET severity=excluded.severity, title=excluded.title",
            (ev.event_id, ev.type, ev.country, ev.lat, ev.lon, str(ev.date), ev.severity, ev.title, ev.url, first_seen.isoformat()),
        )
        con.commit()
    finally:
        _close(con)


def get_events():
    from scorer import Event
    con = _connect()
    try:
        cur = con.execute("SELECT id,type,country,lat,lon,event_date,severity,title,source_url FROM events")
        rows = cur.fetchall()
        out = []
        for r in rows:
            _id, typ, country, lat, lon, dstr, sev, title, url = r[:9]
            try:
                d = date.fromisoformat(dstr)
            except ValueError:
                continue
            out.append(Event(event_id=_id, date=d, issued=d, country=country or "", type=typ,
                             severity=float(sev), lat=float(lat or 0), lon=float(lon or 0),
                             duration_days=3, confidence=0.8, title=title or "", url=url or "", source="store"))
        return out
    finally:
        _close(con)


def update_score(trip_id, leg_id, place, country, lat, lon, start, end, score, tier, driver, updated_at):
    con = _connect()
    try:
        con.execute(
            "INSERT INTO trip_scores (trip_id,leg_id,place,country,lat,lon,start_date,end_date,score,tier,driver,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(trip_id,leg_id) DO UPDATE SET score=excluded.score, tier=excluded.tier, driver=excluded.driver, updated_at=excluded.updated_at",
            (trip_id, leg_id, place, country, lat, lon, str(start), str(end), float(score), tier, driver or "", updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at)),
        )
        con.commit()
    finally:
        _close(con)


def log_alert(d: dict):
    con = _connect()
    try:
        con.execute(
            "INSERT INTO alerts (trip_id,leg_id,kind,tier,prev_tier,text,created_at) VALUES (?,?,?,?,?,?,?)",
            (d.get("trip_id", ""), d.get("leg_id", ""), d.get("kind", ""), d.get("tier", ""), d.get("prev_tier", ""), d.get("text", ""), str(d.get("created_at", ""))),
        )
        con.commit()
    finally:
        _close(con)


def get_alerts(limit=50):
    con = _connect()
    try:
        cur = con.execute("SELECT id,trip_id,leg_id,kind,tier,prev_tier,text,created_at FROM alerts ORDER BY id DESC LIMIT ?", (limit,))
        return [{"id": r[0], "trip_id": r[1], "leg_id": r[2], "kind": r[3], "tier": r[4], "prev_tier": r[5], "text": r[6], "created_at": r[7]} for r in cur.fetchall()]
    finally:
        _close(con)


def upsert_health(feed: str, ok: bool, error: str = ""):
    con = _connect()
    try:
        now = datetime.now().isoformat()
        con.execute(
            "INSERT INTO feed_health (feed,last_ok,last_error,updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(feed) DO UPDATE SET last_ok=excluded.last_ok, last_error=excluded.last_error, updated_at=excluded.updated_at",
            (feed, now if ok else None, error or "", now),
        )
        con.commit()
    finally:
        _close(con)


def get_health():
    con = _connect()
    try:
        cur = con.execute("SELECT feed,last_ok,last_error,updated_at FROM feed_health")
        return [{"feed": r[0], "last_ok": r[1], "last_error": r[2], "updated_at": r[3]} for r in cur.fetchall()]
    finally:
        _close(con)


def get_scores():
    con = _connect()
    try:
        cur = con.execute("SELECT trip_id,leg_id,place,country,lat,lon,start_date,end_date,score,tier,driver,updated_at FROM trip_scores ORDER BY score DESC")
        return [{"trip_id": r[0], "leg_id": r[1], "place": r[2], "country": r[3], "lat": r[4], "lon": r[5], "start": r[6], "end": r[7], "score": r[8], "tier": r[9], "driver": r[10], "updated_at": r[11]} for r in cur.fetchall()]
    finally:
        _close(con)
