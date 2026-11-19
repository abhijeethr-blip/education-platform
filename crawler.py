"""Respectful same-domain crawler with explicit robots/network diagnostics."""
import json,re,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse,urldefrag
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup

OUT=Path('output')
HEADERS={'User-Agent':'EducationDiscoveryBot/0.5 (+contact: site administrator; research indexing)'}
KEYWORDS=('program','course','admission','fee','scholarship','placement','eligibility','pgdm','mba','about','academics')

def host(url):
    return (urlparse(url).hostname or '').lower().removeprefix('www.')

def robots_policy(session,url,cache):
    parsed=urlparse(url);origin=f'{parsed.scheme}://{parsed.netloc}'
    if origin not in cache:
        try:
            response=session.get(origin+'/robots.txt',headers=HEADERS,timeout=12)
            if response.status_code==200:
                parser=RobotFileParser();parser.parse(response.text.splitlines());cache[origin]=('ok',parser)
            elif response.status_code in (404,410):
                cache[origin]=('not_found',None)
            elif response.status_code in (401,403):
                cache[origin]=('robots_denied',None)
            else:
                cache[origin]=('robots_unavailable',f'HTTP {response.status_code}')
        except requests.RequestException as exc:
            cache[origin]=('network_error',str(exc))
    status,detail=cache[origin]
    if status=='ok':return ('allowed' if detail.can_fetch(HEADERS['User-Agent'],url) else 'robots_denied',None)
    if status=='not_found':return ('allowed',None)
    return status,detail if isinstance(detail,str) else None

def crawl_institution(session,name,website,limit=12,delay=1.5):
    if urlparse(website).scheme not in ('http','https') or not host(website):
        raise ValueError('Institution website must be a valid HTTP(S) URL')
    pending=[website];seen=set();pages=[];cache={}
    while pending and len(pages)<limit:
        url=urldefrag(pending.pop(0))[0]
        if url in seen:continue
        seen.add(url)
        if host(url)!=host(website):continue
        status,message=robots_policy(session,url,cache)
        if status!='allowed':
            pages.append({'url':url,'status':status,'message':message or status})
            continue
        try:
            response=session.get(url,headers=HEADERS,timeout=20)
            response.raise_for_status()
            if host(response.url)!=host(website):
                pages.append({'url':url,'status':'external_redirect'});continue
            if 'html' not in response.headers.get('Content-Type','').lower():
                pages.append({'url':url,'status':'unsupported_content_type'});continue
            soup=BeautifulSoup(response.text,'html.parser')
            title=soup.title.get_text(' ',strip=True) if soup.title else ''
            # Collect links before stripping navigation from visible page text.
            links=[]
            for anchor in soup.select('a[href]'):
                link=urldefrag(urljoin(response.url,anchor['href']))[0]
                if urlparse(link).scheme in ('http','https') and host(link)==host(website):
                    if any(term in (link+' '+anchor.get_text(' ',strip=True)).lower() for term in KEYWORDS):links.append(link)
            for tag in soup(['script','style','nav','footer','noscript']):tag.decompose()
            visible=re.sub(r'\s+',' ',soup.get_text(' ',strip=True))
            pages.append({'url':response.url,'status':'fetched','title':title,'text':visible[:60000],
                          'fetched_at':datetime.now(timezone.utc).isoformat()})
            for link in links:
                if link not in seen and link not in pending:pending.append(link)
        except requests.RequestException as exc:
            pages.append({'url':url,'status':'network_error' if isinstance(exc,requests.ConnectionError) else 'fetch_error','message':str(exc)})
        if delay:time.sleep(delay)
    return {'name':name,'website':website,'pages':pages}

if __name__=='__main__':
    import csv
    OUT.mkdir(exist_ok=True)
    with requests.Session() as session,open('institutions.csv',encoding='utf-8',newline='') as f:
        for row in csv.DictReader(f):
            result=crawl_institution(session,row['name'],row['website'])
            slug=re.sub('[^a-z0-9]+','_',row['name'].lower()).strip('_')
            (OUT/(slug+'.json')).write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
            print(row['name'],{p['status'] for p in result['pages']})
