import logging
import psycopg2
import psycopg2.extras
from config import DATABASE_URL

logger = logging.getLogger("price-tracker.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS watches (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    url TEXT NOT NULL,
    css_selector VARCHAR(500),
    tag_name VARCHAR(100),
    attribute_filter VARCHAR(255),
    threshold_below NUMERIC(12,2),
    threshold_above NUMERIC(12,2),
    threshold_pct NUMERIC(5,2),
    currency VARCHAR(10) DEFAULT 'RUB',
    is_active BOOLEAN DEFAULT true,
    check_interval INTEGER DEFAULT 300,
    last_price NUMERIC(12,2),
    last_checked TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS price_history (
    id SERIAL PRIMARY KEY,
    watch_id INTEGER REFERENCES watches(id) ON DELETE CASCADE,
    price NUMERIC(12,2) NOT NULL,
    raw_text TEXT,
    recorded_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts_log (
    id SERIAL PRIMARY KEY,
    watch_id INTEGER REFERENCES watches(id) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL,
    message TEXT,
    price NUMERIC(12,2),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ph_watch ON price_history(watch_id);
CREATE INDEX IF NOT EXISTS idx_ph_time ON price_history(recorded_at);
CREATE INDEX IF NOT EXISTS idx_watches_active ON watches(is_active);
CREATE INDEX IF NOT EXISTS idx_alerts_watch ON alerts_log(watch_id);
"""


def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(SCHEMA_SQL)
    cur.close()
    conn.close()
    logger.info("Database initialized")
