"""Read article-specific publisher preview metadata; no generic journal artwork."""
import json
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
class Metadata(HTMLParser):
    def __init__(self):
        super().__init__(); self.image = None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta' and a.get('property', a.get('name','')) in ('og:image','twitter:image'):
            url = a.get('content','')
            if url.startswith('https://') and not any(s in url.lower() for s in ('logo','default','cover','arxiv','social','journal-header')):
                self.image = self.image or url

def enrich(p):
    if p.get('image'): return p
    try:
        request = urllib.request.Request(p['url'], headers={'User-Agent':'Mozilla/5.0 (ResearchDaily article preview)'})
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read(2000000).decode('utf-8', errors='replace')
        parser = Metadata(); parser.feed(raw)
        if parser.image:
            p.update(image=parser.image, image_label='出版商文章预览', image_source=p['url'])
    except Exception:
        pass
    return p

def main():
    path = ROOT/'site/data/articles.json'
    papers = json.loads(path.read_text())
    candidates = [p for p in papers if p.get('relevance',0)>=80 and p.get('journal')][:30]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(enrich, candidates))
    path.write_text(json.dumps(papers, ensure_ascii=False, indent=2)+'\n')
    print('Article previews:',sum(bool(p.get('image')) for p in papers))
if __name__ == '__main__': main()
