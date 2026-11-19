"""Load crawler JSON into PostgreSQL and derive source-linked, UNVERIFIED facts.
No model calls and no invented values. Facts are candidate text snippets for review.
"""
import argparse
import json
import os
import re
from pathlib import Path

PATTERNS = {
    'fees': re.compile(r'\b(?:tuition fees?|total fees?|programme fees?|program fees?|fee structure)\b', re.I),
    'eligibility': re.compile(r'\b(?:eligibility|minimum qualification|bachelor.s degree)\b', re.I),
    'placements': re.compile(r'\b(?:placements?|average package|highest package|median salary)\b', re.I),
    'scholarships': re.compile(r'\b(?:scholarships?|financial aid|merit award)\b', re.I),
    'admissions': re.compile(r'\b(?:admission process|selection process|entrance exam)\b', re.I),
    'duration': re.compile(r'\b(?:two.year|2.year|duration|trimesters?|semesters?)\b', re.I),
}

def extract_candidates(text):
    """Conservative candidate snippets, not normalized or verified facts."""
    snippets = {}
    for key, pattern in PATTERNS.items():
        match = pattern.search(text or '')
        if match:
            snippets[key] = (text[max(0, match.start()-65):match.end()+175]).strip()
    return snippets

def ingest(conn, record):
    name, website = record['name'], record['website']
    with conn.cursor() as cur:
        cur.execute('''INSERT INTO edu.institutions(name,website) VALUES (%s,%s)
          ON CONFLICT(website) DO UPDATE SET name=EXCLUDED.name,updated_at=now()
          RETURNING id''', (name, website))
        institution_id = cur.fetchone()[0]
        page_count, fact_count = 0, 0
        for page in record.get('pages', []):
            if not page.get('url'):
                continue
            cur.execute('''INSERT INTO edu.source_pages
             (institution_id,url,fetched_at,status,title,extracted_text,metadata)
             VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
             ON CONFLICT(institution_id,url) DO UPDATE SET
              fetched_at=EXCLUDED.fetched_at,status=EXCLUDED.status,
              title=EXCLUDED.title,extracted_text=EXCLUDED.extracted_text,
              metadata=EXCLUDED.metadata RETURNING id''',
              (institution_id,page['url'],page.get('fetched_at'),page.get('status','unknown'),
               page.get('title'),page.get('text'),json.dumps({'message':page.get('message')})))
            page_id = cur.fetchone()[0]
            page_count += 1
            # On recrawl, remove old unverified candidates for this source.
            cur.execute("DELETE FROM edu.facts WHERE source_page_id=%s AND review_status='unverified'", (page_id,))
            if page.get('status') != 'fetched':
                continue
            for field, snippet in extract_candidates(page.get('text','')).items():
                cur.execute('''INSERT INTO edu.facts(institution_id,field_key,field_value,source_page_id)
                 VALUES (%s,%s,%s::jsonb,%s)
                 ON CONFLICT(institution_id,field_key,source_page_id) DO NOTHING''',
                 (institution_id,field,json.dumps({'candidate_text':snippet}),page_id))
                fact_count += cur.rowcount
    return page_count, fact_count

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='output', help='Directory of crawler JSON files')
    parser.add_argument('--dsn', default=os.environ.get('DATABASE_URL'), help='PostgreSQL DSN (or DATABASE_URL)')
    args = parser.parse_args()
    if not args.dsn:
        parser.error('Set DATABASE_URL or pass --dsn; no database changes made.')
    import psycopg
    with psycopg.connect(args.dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(Path(__file__).with_name('schema.sql').read_text())
        for path in sorted(Path(args.input).glob('*.json')):
            try:
                record = json.loads(path.read_text(encoding='utf-8'))
                pages, facts = ingest(conn,record)
                conn.commit()
                print(f'{record["name"]}: {pages} source pages; {facts} unverified candidate facts')
            except Exception:
                conn.rollback()
                raise

if __name__ == '__main__':
    main()
