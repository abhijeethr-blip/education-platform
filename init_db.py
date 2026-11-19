"""One-time schema initialization, run as a Railway service command or locally."""
import csv
import gzip
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
        cur.execute("""
            SELECT pg_cancel_backend(pid) FROM pg_stat_activity
            WHERE pid <> pg_backend_pid() AND datname = current_database()
              AND usename = current_user AND state = 'active'
              AND query LIKE '%UPDATE edu.institutions AS existing SET aishe_id%'
              AND query LIKE '%SELECT count(*) FROM aishe_import matching%'
              AND query NOT LIKE '%pg_cancel_backend%'
        """)
        cur.execute(Path(__file__).with_name('schema.sql').read_text())
        cur.executemany(
            'INSERT INTO edu.institutions (name, website) VALUES (%s, %s) '
            'ON CONFLICT (website) DO NOTHING',
            institutions,
        )
        catalog = Path(__file__).with_name('aishe_catalog.csv.gz')
        if catalog.exists():
            cur.execute('SELECT pg_advisory_xact_lock(918362)')
            cur.execute('ALTER TABLE edu.institutions ADD COLUMN IF NOT EXISTS aishe_id text UNIQUE')
            cur.execute('ALTER TABLE edu.institutions ALTER COLUMN website DROP NOT NULL')
            cur.execute("""CREATE TEMP TABLE aishe_import (
                aishe_id text PRIMARY KEY, name text, state text, district text,
                website text, category text, institution_type text, specialization text
            ) ON COMMIT DROP""")
            with gzip.open(catalog, 'rb') as dataset:
                with cur.copy('COPY aishe_import FROM STDIN WITH (FORMAT CSV, HEADER)') as copy:
                    while chunk := dataset.read(256 * 1024):
                        copy.write(chunk)
            cur.execute("""
                WITH distinct_sites AS (
                    SELECT rtrim(website, '/') AS website, min(aishe_id) AS aishe_id
                    FROM aishe_import
                    WHERE website IS NOT NULL
                    GROUP BY rtrim(website, '/')
                    HAVING count(*) = 1
                )
                UPDATE edu.institutions AS existing SET aishe_id = incoming.aishe_id
                FROM distinct_sites AS incoming
                WHERE existing.aishe_id IS NULL AND existing.website IS NOT NULL
                  AND rtrim(existing.website, '/') = incoming.website
                  AND NOT EXISTS (SELECT 1 FROM edu.institutions imported
                                  WHERE imported.aishe_id = incoming.aishe_id)
            """)
            cur.execute("""
                INSERT INTO edu.institutions (aishe_id, name, state, city, attributes)
                SELECT aishe_id, COALESCE(NULLIF(btrim(name), ''), 'Institution ' || aishe_id), state, district,
                       jsonb_strip_nulls(jsonb_build_object(
                           'aishe_website', website, 'category', category,
                           'institution_type', institution_type,
                           'specialization', specialization))
                FROM aishe_import
                ON CONFLICT (aishe_id) DO UPDATE SET
                    name = EXCLUDED.name, state = EXCLUDED.state, city = EXCLUDED.city,
                    attributes = edu.institutions.attributes || EXCLUDED.attributes
                WHERE (edu.institutions.name, edu.institutions.state, edu.institutions.city,
                       edu.institutions.attributes)
                      IS DISTINCT FROM
                      (EXCLUDED.name, EXCLUDED.state, EXCLUDED.city,
                       edu.institutions.attributes || EXCLUDED.attributes)
            """)
            cur.execute('SELECT count(*) FROM aishe_import')
            print(f'Loaded {cur.fetchone()[0]} AISHE directory records')
print('Education database schema and institution directory initialized')
