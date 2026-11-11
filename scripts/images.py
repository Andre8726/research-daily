"""Attach article-specific preview figures.

Order of sources (no bot-protection bypassing, no generic journal artwork):
1. arXiv preprints: first figure of the arXiv HTML full text.
2. Journal articles: publisher og:image / twitter:image (works for e.g. Springer Nature, Frontiers).
3. Journal articles without one: matching arXiv version found via Semantic Scholar, then (1).
Results are cached in articles.json; misses are retried after RETRY_DAYS.
"""
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {'User-Agent': 'ResearchDaily/1.0 (academic article preview; https://andre8726.github.io/research-daily/)'}
RETRY_DAYS = 7
SKIP_WORDS = ('logo', 'default', 'cover', 'arxiv', 'social', 'journal-header')


def fetch(url, limit=4_000_000, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as response:
        return response.geturl(), response.read(limit).decode('utf-8', errors='replace')


class MetaImage(HTMLParser):
    def __init__(self):
        super().__init__(); self.image = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta' and a.get('property', a.get('name', '')) in ('og:image', 'twitter:image'):
            url = a.get('content') or ''
            if url.startswith('https://') and not any(s in url.lower() for s in SKIP_WORDS):
                self.image = self.image or url


class FirstFigure(HTMLParser):
    def __init__(self):
        super().__init__(); self.depth = 0; self.image = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'figure':
            self.depth += 1
        src = a.get('src') or ''
        if tag == 'img' and self.depth and not self.image and src and not src.lower().endswith('.svg'):
            self.image = src

    def handle_endtag(self, tag):
        if tag == 'figure':
            self.depth = max(0, self.depth - 1)


def arxiv_id(p):
    return p['id'] if 'arxiv.org/abs/' in p.get('url', '') else p.get('arxiv_id')


def arxiv_figure(aid):
    final, raw = fetch(f'https://arxiv.org/html/{aid}')
    parser = FirstFigure(); parser.feed(raw)
    if parser.image:
        url = urllib.parse.urljoin(final, parser.image)
        if url.startswith('https://arxiv.org/'):
            return url


def publisher_image(url):
    _, raw = fetch(url, limit=2_000_000, timeout=15)
    parser = MetaImage(); parser.feed(raw)
    return parser.image


def lookup_arxiv_ids(papers):
    """Map DOI journal papers to arXiv versions in one Semantic Scholar batch call (best effort)."""
    todo = [p for p in papers if p.get('doi') and 'arxiv_id' not in p]
    for start in range(0, len(todo), 400):
        chunk = todo[start:start + 400]
        request = urllib.request.Request(
            'https://api.semanticscholar.org/graph/v1/paper/batch?fields=externalIds',
            data=json.dumps({'ids': ['DOI:' + p['doi'] for p in chunk]}).encode(),
            headers={**UA, 'Content-Type': 'application/json'})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    found = json.load(response)
                break
            except Exception as error:
                if attempt == 3:
                    print('Semantic Scholar lookup skipped, will retry next run:', error)
                    return
                time.sleep(10 * (attempt + 1))
        for p, item in zip(chunk, found):
            p['arxiv_id'] = ((item or {}).get('externalIds') or {}).get('ArXiv') or ''


def enrich(p):
    try:
        if 'arxiv.org/abs/' in p.get('url', ''):
            image = arxiv_figure(p['id'])
            if image:
                return p.update(image=image, image_label='arXiv 论文插图', image_source=f"https://arxiv.org/html/{p['id']}")
        else:
            try:
                image = publisher_image(p['url'])
            except Exception:
                image = None
            if image:
                return p.update(image=image, image_label='出版商文章预览', image_source=p['url'])
            if p.get('arxiv_id'):
                image = arxiv_figure(p['arxiv_id'])
                if image:
                    return p.update(image=image, image_label='arXiv 版本论文插图', image_source=f"https://arxiv.org/html/{p['arxiv_id']}")
    except Exception:
        pass
    if 'arxiv.org/abs/' in p.get('url', '') or 'arxiv_id' in p:
        p['image_checked'] = date.today().isoformat()  # journal papers whose arXiv lookup failed retry tomorrow


def due(p):
    if p.get('image') or p.get('relevance', 0) < 80:
        return False
    checked = p.get('image_checked')
    return not checked or date.fromisoformat(checked) <= date.today() - timedelta(days=RETRY_DAYS)


def main():
    path = ROOT / 'site/data/articles.json'
    papers = json.loads(path.read_text())
    candidates = [p for p in papers if due(p)]
    lookup_arxiv_ids([p for p in candidates if p.get('journal')])
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(enrich, candidates))
    path.write_text(json.dumps(papers, ensure_ascii=False, indent=2) + '\n')
    related = [p for p in papers if p.get('relevance', 0) >= 80]
    print(f'Checked {len(candidates)}; related papers with previews: {sum(bool(p.get("image")) for p in related)}/{len(related)}')


if __name__ == '__main__':
    main()
