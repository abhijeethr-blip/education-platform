import sys,unittest
from pathlib import Path
from unittest.mock import Mock
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler import crawl_institution

class Session:
 def __init__(self,robots_status=200):self.urls=[];self.robots_status=robots_status
 def get(self,url,**kw):
  self.urls.append(url)
  r=Mock();r.status_code=self.robots_status if url.endswith('/robots.txt') else 200;r.url=url
  r.headers={'Content-Type':'text/html'}
  if url.endswith('/robots.txt'):r.text='User-agent: *\nAllow: /\n'
  elif url.endswith('/fees'):r.text='<title>Fees</title><main>Programme fee INR 900000</main>'
  else:r.text='<title>College</title><nav><a href="/fees">Fees</a></nav><main>Eligibility Bachelor degree</main>'
  r.raise_for_status=lambda:None
  return r

class TestCrawler(unittest.TestCase):
 def test_nav_discovery_and_robots_cached(self):
  s=Session();r=crawl_institution(s,'Example','https://example.edu/',limit=3,delay=0)
  self.assertEqual(sum(p['status']=='fetched' for p in r['pages']),2)
  self.assertEqual(s.urls.count('https://example.edu/robots.txt'),1)
  self.assertIn('Programme fee',r['pages'][1]['text'])
 def test_robots_denied(self):
  r=crawl_institution(Session(403),'Example','https://example.edu/',delay=0)
  self.assertEqual(r['pages'][0]['status'],'robots_denied')
 def test_dns_error_is_not_robots_denial(self):
  class Broken:
   def get(self,*a,**k):raise requests.ConnectionError('DNS resolution failed')
  r=crawl_institution(Broken(),'Example','https://example.edu/',delay=0)
  self.assertEqual(r['pages'][0]['status'],'network_error')
 def test_no_cross_domain(self):
  s=Session();r=crawl_institution(s,'Example','https://example.edu/',delay=0)
  self.assertTrue(all('example.edu' in u for u in s.urls))
if __name__=='__main__':unittest.main()
