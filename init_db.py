"""One-time schema initialization, run as a Railway service command or locally."""
import csv
import os
from pathlib import Path
import psycopg
url = os.environ.get('DATABASE_URL')
if not url:
    raise SystemExit('DATABASE_URL is required')
with Path(__file__).with_name('institutions.csv').open(encoding='utf-8', newline='') as source:
    institutions = [(row['name'], row['website']) for row in csv.DictReader(source)]

with psycopg.connect(url) as conn:
    with conn.cursor() as cur:
        cur.execute(Path(__file__).with_name('schema.sql').read_text())
        cur.executemany(
            'INSERT INTO edu.institutions (name, website) VALUES (%s, %s) '
            'ON CONFLICT (website) DO NOTHING',
            institutions,
        )
print('Education database schema and institution directory initialized')
