"""Batch orchestrator: resumable, bounded parallelism, per-site crawl policy from crawler.py."""
import argparse,csv,json,re,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import requests
from crawler import crawl_institution

def run(csv_path='institutions.csv',out='output',workers=3,limit=12,force=False):
    destination=Path(out);destination.mkdir(parents=True,exist_ok=True)
    with open(csv_path,encoding='utf-8',newline='') as f: rows=list(csv.DictReader(f))
    rows=[r for r in rows if r.get('name') and r.get('website','').startswith(('https://','http://'))]
    def task(row):
        slug=re.sub('[^a-z0-9]+','_',row['name'].lower()).strip('_')
        path=destination/(slug+'.json')
        if path.exists() and not force:return {'name':row['name'],'status':'skipped','pages':0}
        try:
            with requests.Session() as session: result=crawl_institution(session,row['name'],row['website'],limit)
            temp=path.with_suffix('.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)
            return {'name':row['name'],'status':'saved','pages':len(result['pages']),'fetched':sum(x.get('status')=='fetched' for x in result['pages'])}
        except Exception as e:return {'name':row['name'],'status':'error','error':str(e)}
    start=time.time();results=[]
    with ThreadPoolExecutor(max_workers=min(max(1,workers),5)) as pool:
        for future in as_completed([pool.submit(task,r) for r in rows]):
            item=future.result();results.append(item);print(json.dumps(item),flush=True)
    summary={'institutions':len(rows),'saved':sum(r['status']=='saved' for r in results),'skipped':sum(r['status']=='skipped' for r in results),'errors':sum(r['status']=='error' for r in results),'fetched_pages':sum(r.get('fetched',0) for r in results),'seconds':round(time.time()-start,1),'results':results}
    (destination/'batch_report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--csv',default='institutions.csv');a.add_argument('--out',default='output');a.add_argument('--workers',type=int,default=3);a.add_argument('--limit',type=int,default=12);a.add_argument('--force',action='store_true');args=a.parse_args();run(args.csv,args.out,args.workers,args.limit,args.force)
