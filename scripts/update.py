"""Fetch arXiv metadata; only replace public data after all queries succeed."""
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from ranking import select
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUERIES = {
    'altermagnetism': '(all:altermagnet OR all:altermagnetism OR all:altermagnon) AND (all:spin OR all:magnon)',
    'Kagome 反铁磁': '(all:kagome AND (all:antiferromagnet OR all:antiferromagnetic OR all:Mn3Sn OR all:Mn3Ge))',
    '自旋存储': '(all:spintronics OR all:MRAM OR all:"spin orbit torque" OR all:"spin transfer torque") AND (all:memory OR all:memories OR all:switching)',
    'AI for spintronics': '(all:spintronics OR all:spintronic OR all:skyrmion OR all:"magnetic tunnel junction") AND (all:"machine learning" OR all:"deep learning" OR all:"artificial intelligence" OR all:"neural network" OR all:"reinforcement learning")',
}
NS = {'a': 'http://www.w3.org/2005/Atom'}
KEEP = ('image', 'image_label', 'image_source', 'image_checked', 'arxiv_id')  # cached by images.py

def keep_cached(new, previous):
    for key in KEEP:
        if previous and key in previous and key not in new:
            new[key] = previous[key]
    return new

def parse_feed(raw, tag):
    root = ET.fromstring(raw)
    papers = []
    for entry in root.findall('a:entry', NS):
        def value(name):
            return ' '.join(entry.findtext('a:' + name, '', NS).split())
        url = value('id')
        if '/api/errors' in url:
            raise ValueError(value('summary'))
        if not url.startswith(('https://arxiv.org/abs/', 'http://arxiv.org/abs/')):
            raise ValueError('Unexpected arXiv identifier')
        papers.append(dict(id=re.sub(r'v\d+$', '', url.rsplit('/', 1)[-1]),
                           title=value('title'), summary=value('summary'),
                           date=value('published')[:10], updated=value('updated'),
                           url=url.replace('http:', 'https:'), tags=[tag], source='arXiv · 预印本',
                           authors=[a.findtext('a:name', '', NS) for a in entry.findall('a:author', NS)]))
    return papers

def journals():
    found = []
    today = datetime.now(timezone.utc).date()
    queries = ['kagome antiferromagnet', 'spin orbit torque memory', 'spintronics machine learning', 'magnetic tunnel junction neural network', 'altermagnetism magnon']
    requests = [(query, '') for query in queries]
    # Target each flagship journal independently so broad-query result caps cannot crowd it out.
    for issn in ['0036-8075', '0028-0836', '1745-2473']:
        requests.extend((query, ',issn:'+issn) for query in queries)
    for query, journal_filter in requests:
        params = urllib.parse.urlencode({'query': query, 'filter': f'type:journal-article,from-pub-date:{today-timedelta(days=90)},until-pub-date:{today}{journal_filter}', 'rows': 60})
        req = urllib.request.Request('https://api.crossref.org/works?' + params, headers={'User-Agent':'ResearchDaily/1.0'})
        with urllib.request.urlopen(req, timeout=60) as response:
            items = json.load(response)['message']['items']
        for item in items:
            if not item.get('title') or not item.get('DOI'): continue
            parts = (item.get('published-online') or item.get('published') or {}).get('date-parts', [[today.year]])[0]
            day = '-'.join(str(n).zfill(2) for n in (parts + [1,1])[:3])
            if day > str(today): continue
            journal = (item.get('container-title') or [''])[0]
            found.append(dict(id=item['DOI'].lower(), doi=item['DOI'], title=item['title'][0],
                summary=html.unescape(re.sub('<[^>]+>', ' ', item.get('abstract',''))).strip(),
                date=day, url='https://doi.org/'+item['DOI'], journal=journal,
                source=journal or '期刊论文', tags=[], authors=[]))
        time.sleep(1)
    return found

def main():
    path = ROOT / 'site/data/articles.json'
    papers = {p['id']: p for p in json.loads(path.read_text())}
    for tag, query in QUERIES.items():
        params = urllib.parse.urlencode(dict(search_query=query, start=0, max_results=60,
                                             sortBy='submittedDate', sortOrder='descending'))
        request = urllib.request.Request('https://export.arxiv.org/api/query?' + params,
                                         headers={'User-Agent': 'ResearchDaily/1.0 (academic metadata reader)'})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    found = parse_feed(response.read(), tag)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(5 * (attempt + 1))
        for p in found:
            previous = papers.get(p['id'])
            if previous:
                p['tags'] = sorted(set(previous['tags'] + p['tags']))
            papers[p['id']] = keep_cached(p, previous)
        time.sleep(3)
    for p in journals():
        papers[p['id']] = keep_cached(p, papers.get(p['id']))
    result = select(papers.values())
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    (ROOT / 'site/data/status.json').write_text(json.dumps({
        'updated_at': datetime.now(timezone.utc).isoformat(), 'count': len(result),
        'source': 'Crossref + arXiv', 'topics': list(QUERIES)
    }, ensure_ascii=False, indent=2) + '\n')
    print(f'Updated {len(result)} papers')

if __name__ == '__main__':
    main()
