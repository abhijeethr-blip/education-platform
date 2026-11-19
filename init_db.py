"""One-time schema initialization, run as a Railway service command or locally."""
import os
from pathlib import Path
import psycopg
url = os.environ.get('DATABASE_URL')
if not url:
    raise SystemExit('DATABASE_URL is required')
with psycopg.connect(url) as conn:
    with conn.cursor() as cur:
        cur.execute(Path(__file__).with_name('schema.sql').read_text())
print('Education database schema initialized')
