"""Crawl bounded batches from a registry-backed allowlist and save progress in PostgreSQL."""
import json
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit

import psycopg
import requests
from bs4 import BeautifulSoup

from crawler import crawl_institution, host
from pipeline import extract_candidates

REGISTRY = 'https://josaa.admissions.nic.in/applicant/seatmatrix/instituteview.aspx'
WORKERS = 6
BATCH_SIZE = 24
RECRAWL_DAYS = 30


class InstitutionSession(requests.Session):
    def __init__(self, website):
        super().__init__()
        self.institution_host = host(website)
        self.max_redirects = 5

    def request(self, method, url, *args, **kwargs):
        self.check_url(url)
        return super().request(method, url, *args, **kwargs)

    def check_url(self, url):
        destination = urlsplit(url)
        if (destination.scheme not in ('http', 'https')
                or host(destination.geturl()) != self.institution_host
                or destination.username or destination.password
                or destination.port not in (None, 80, 443)):
            raise requests.RequestException('Request outside the approved institution host')

    def get_redirect_target(self, response):
        target = super().get_redirect_target(response)
        if target:
            self.check_url(urljoin(response.url, target))
        return target


def official_sites():
    response = requests.get(REGISTRY, timeout=20, allow_redirects=False)
    if response.status_code != 200:
        raise RuntimeError(f'JoSAA registry returned HTTP {response.status_code}')
    sites = {}
    for row in BeautifulSoup(response.text, 'html.parser').find_all('tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells) < 5:
            continue
        match = re.search(r'Website:\s*(?:https?://)?([a-z0-9.-]+\.[a-z]{2,})', cells[4].get_text(' ', strip=True), re.I)
        if match:
            domain = match[1].lower()
            sites[domain.removeprefix('www.')] = f'https://{domain}/'
    if not sites:
        raise RuntimeError('No websites found in the JoSAA registry')
    return sites


def crawl(job):
    institution_id, name, website = job
    with InstitutionSession(website) as session:
        try:
            pages = crawl_institution(session, name, website, limit=4)['pages']
        except ValueError:
            pages = []
    return institution_id, [page for page in pages if page['status'] == 'fetched']


def save(conn, institution_id, pages):
    for page in pages:
        page_id = conn.execute(
            """INSERT INTO edu.source_pages
               (institution_id,url,fetched_at,status,title)
               VALUES (%s,%s,%s,'fetched',%s)
               ON CONFLICT (institution_id,url) DO UPDATE SET
                   fetched_at=EXCLUDED.fetched_at,status='fetched',title=EXCLUDED.title
               RETURNING id""",
            (institution_id, page['url'], page['fetched_at'], page['title']),
        ).fetchone()[0]
        conn.execute("DELETE FROM edu.facts WHERE source_page_id=%s AND review_status='unverified'", (page_id,))
        for field, snippet in extract_candidates(page['text']).items():
            conn.execute(
                """INSERT INTO edu.facts (institution_id,field_key,field_value,source_page_id)
                   VALUES (%s,%s,%s::jsonb,%s)
                   ON CONFLICT (institution_id,field_key,source_page_id) DO NOTHING""",
                (institution_id, field, json.dumps({'candidate_text': snippet}), page_id),
            )
    conn.execute(
        """INSERT INTO edu.crawl_progress (institution_id,attempted_at,pages_fetched)
           VALUES (%s,now(),%s) ON CONFLICT (institution_id) DO UPDATE SET
           attempted_at=now(),pages_fetched=EXCLUDED.pages_fetched""",
        (institution_id, len(pages)),
    )
    conn.commit()


def main():
    registry = official_sites()
    with psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=15) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS edu.crawl_progress (
                institution_id bigint PRIMARY KEY REFERENCES edu.institutions(id) ON DELETE CASCADE,
                attempted_at timestamptz NOT NULL, pages_fetched integer NOT NULL
            )"""
        )
        rows = conn.execute(
            """SELECT i.id,i.name,COALESCE(i.website,i.attributes->>'aishe_website'),p.attempted_at,
                      p.attempted_at IS NULL OR p.attempted_at < now()-(%s * interval '1 day')
               FROM edu.institutions i LEFT JOIN edu.crawl_progress p ON p.institution_id=i.id
               ORDER BY p.attempted_at NULLS FIRST,i.id""", (RECRAWL_DAYS,)
        ).fetchall()
        conn.commit()
        matches = []
        for institution_id, name, website, _, due in rows:
            try:
                domain = host(website or '')
            except ValueError:
                continue
            if domain in registry:
                matches.append((institution_id, name, domain, due))
        counts = Counter(domain for _, _, domain, _ in matches)
        jobs = [(i, name, registry[d]) for i, name, d, due in matches if due and counts[d] == 1][:BATCH_SIZE]
        completed = 0
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for institution_id, pages in pool.map(crawl, jobs):
                save(conn, institution_id, pages)
                completed += len(pages)
        print(f'Catalog: {len(rows)} records. Registry matches: {len(matches)}. Attempted: {len(jobs)}. Pages: {completed}.')


if __name__ == '__main__':
    main()
