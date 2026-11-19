"""Read-only local website/API backed by PostgreSQL. No demo data substitution."""
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).parent / 'web'


def fetch_profiles(dsn, query='', limit=100):
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute('''SELECT i.id,i.name,i.website,i.city,i.state,i.country,
              COUNT(DISTINCT s.id)::integer AS source_count,
              COUNT(DISTINCT f.id)::integer AS candidate_count
              FROM edu.institutions i LEFT JOIN edu.source_pages s ON s.institution_id=i.id
              LEFT JOIN edu.facts f ON f.institution_id=i.id
              WHERE i.name ILIKE %s GROUP BY i.id ORDER BY i.name LIMIT %s''',
              (f'%{query}%', min(max(int(limit),1),500)))
            return cur.fetchall()


def fetch_profile(dsn, institution_id):
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT id,name,website,city,state,country FROM edu.institutions WHERE id=%s', (institution_id,))
            institution=cur.fetchone()
            if not institution: return None
            cur.execute('''SELECT f.field_key,f.field_value,f.review_status,s.url,s.fetched_at
                FROM edu.facts f JOIN edu.source_pages s ON s.id=f.source_page_id
                WHERE f.institution_id=%s ORDER BY f.field_key,s.fetched_at DESC NULLS LAST LIMIT 200''', (institution_id,))
            institution['facts']=cur.fetchall()
            return institution

def fetch_comparison(dsn, ids):
    import psycopg
    from psycopg.rows import dict_row
    ids=list(dict.fromkeys(ids))[:3]
    if not ids:return []
    with psycopg.connect(dsn,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT id,name,website,city,state,country FROM edu.institutions WHERE id=ANY(%s) ORDER BY name',(ids,))
            institutions=cur.fetchall()
            cur.execute("""SELECT DISTINCT ON (f.institution_id,f.field_key) f.institution_id,f.field_key,f.field_value,s.url
                FROM edu.facts f JOIN edu.source_pages s ON s.id=f.source_page_id
                WHERE f.institution_id=ANY(%s) AND f.review_status='verified'
                ORDER BY f.institution_id,f.field_key,f.extracted_at DESC""",(ids,))
            facts=cur.fetchall()
            for item in institutions:
                item['verified_facts']={f['field_key']:{'value':f['field_value'],'source':f['url']} for f in facts if f['institution_id']==item['id']}
            return institutions

def review_candidates(dsn,limit=100):
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(dsn,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT f.id,i.name,f.field_key,f.field_value,s.url,f.review_status
              FROM edu.facts f JOIN edu.institutions i ON i.id=f.institution_id
              JOIN edu.source_pages s ON s.id=f.source_page_id
              WHERE f.review_status='unverified' ORDER BY f.extracted_at DESC LIMIT %s""",(min(max(limit,1),500),))
            return cur.fetchall()

def set_review(dsn,fact_id,status,normalized_value=None):
    if status not in ('verified','rejected'):raise ValueError('Invalid status')
    if status=='verified' and (not isinstance(normalized_value,str) or not normalized_value.strip()):raise ValueError('A reviewed value is required')
    import psycopg
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            if status=='verified':
                if not isinstance(normalized_value,str) or not normalized_value.strip():raise ValueError('A reviewed value is required')
                cur.execute("UPDATE edu.facts SET review_status=%s,field_value=%s::jsonb WHERE id=%s AND review_status='unverified' RETURNING id",(status,json.dumps({'value':normalized_value.strip()}),fact_id))
            else:
                cur.execute("UPDATE edu.facts SET review_status=%s WHERE id=%s AND review_status='unverified' RETURNING id",(status,fact_id))
            return cur.fetchone() is not None

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(ROOT),**kwargs)

    def do_GET(self):
        url=urlparse(self.path)
        if url.path == '/health':
            return self.respond({'status':'ok'})
        if url.path.startswith('/api/'):
            if url.path.startswith('/api/admin/') and os.environ.get('ENABLE_ADMIN','false').lower() != 'true':
                return self.respond({'error':'Admin API disabled on public deployment'},403)
            try:
                dsn=os.environ.get('DATABASE_URL')
                if not dsn: raise RuntimeError('DATABASE_URL is not configured')
                if url.path=='/api/compare':
                    raw=parse_qs(url.query).get('ids',[''])[0]
                    ids=[int(x) for x in raw.split(',') if x.strip().isdigit()][:3]
                    result=fetch_comparison(dsn,ids)
                elif url.path=='/api/admin/candidates':
                    if not self.is_admin():return self.respond({'error':'Unauthorized'},401)
                    result=review_candidates(dsn)
                elif url.path=='/api/institutions':
                    params=parse_qs(url.query)
                    result=fetch_profiles(dsn,params.get('q',[''])[0])
                elif url.path.startswith('/api/institutions/'):
                    result=fetch_profile(dsn,int(url.path.rsplit('/',1)[-1]))
                    if result is None: return self.respond({'error':'Not found'},404)
                else: return self.respond({'error':'Unknown endpoint'},404)
                return self.respond(result)
            except Exception as exc:
                return self.respond({'error':'Service temporarily unavailable'},503)
        return super().do_GET()

    def is_admin(self):
        import hmac
        token=os.environ.get('ADMIN_TOKEN','')
        provided=self.headers.get('X-Admin-Token','')
        return bool(token) and hmac.compare_digest(token,provided)

    def do_POST(self):
        if self.path!='/api/admin/review':return self.respond({'error':'Unknown endpoint'},404)
        if os.environ.get('ENABLE_ADMIN','false').lower() != 'true':return self.respond({'error':'Admin API disabled on public deployment'},403)
        if not self.is_admin():return self.respond({'error':'Unauthorized'},401)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>10000:return self.respond({'error':'Invalid body length'},400)
            data=json.loads(self.rfile.read(size))
            changed=set_review(os.environ['DATABASE_URL'],int(data['fact_id']),data['status'],data.get('value'))
            return self.respond({'updated':changed},200 if changed else 404)
        except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e:
            return self.respond({'error':str(e)},400)
        except Exception:return self.respond({'error':'Service temporarily unavailable'},503)

    def respond(self,data,status=200):
        from datetime import date,datetime
        payload=json.dumps(data,default=lambda o:o.isoformat() if isinstance(o,(date,datetime)) else str(o)).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

if __name__=='__main__':
    port=int(os.environ.get('PORT','8080'))
    print(f'Open http://localhost:{port} in your browser')
    ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
