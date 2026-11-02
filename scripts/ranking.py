"""Transparent heuristic: topic gate first, journal preference second (not JIF)."""
import re
from datetime import date
PRIORITY = {'nature','science','nature physics','nature materials','nature electronics','nature nanotechnology','nature communications','science advances','advanced materials','advanced functional materials','physical review letters','physical review x','acs nano','nano letters','npj spintronics'}

def matches(text, pattern):
    return bool(re.search(pattern, text, re.I))

def rank(p):
    t = p['title'].lower(); text = t + ' ' + p.get('summary','').lower()
    groups = []
    if matches(text,r'kagome|mn3sn|mn3ge|mn.?3.?sn|mn.?3.?ge') and matches(text,r'antiferromag|mn3sn|mn3ge|mn.?3.?sn|mn.?3.?ge'):
        groups.append(('Kagome 反铁磁',r'kagome|mn.?3.?sn|mn.?3.?ge'))
    if matches(text,r'spintronic|spin.orbit torque|spin.transfer torque|\bmram\b|magnetic tunnel junction|spin.torque') and matches(text,r'memor|switching|\bmram\b'):
        groups.append(('自旋存储',r'memor|\bmram\b|switching'))
    # A skyrmion mention alone is insufficient: require explicit spintronic/device context.
    if matches(text,r'spintronic|magnetic tunnel junction|\bmram\b|spin.orbit torque|spin.transfer torque') and matches(text,r'machine learning|deep learning|artificial intelligence|neural network|reinforcement learning'):
        groups.append(('AI for spintronics',r'machine learning|deep learning|artificial intelligence|neural network|reinforcement learning'))
    p['tags'] = [g[0] for g in groups]
    relevance = (80 + 15 * any(matches(t,g[1]) for g in groups)) if groups else 0
    journal = p.get('journal','')
    prestige = 100 if journal.lower() in PRIORITY else 45 if journal else 0
    try: age=max(0,(date.today()-date.fromisoformat(p['date'])).days)
    except ValueError: age=9999
    fresh=max(0,100-age*100/90)
    p.update(relevance=relevance, score=round(.7*relevance+.2*prestige+.1*fresh,1), journal_priority=journal.lower() in PRIORITY)
    p['reason'] = '；'.join(p['tags']) + ('；重点关注期刊' if p['journal_priority'] else '；期刊论文' if journal else '；预印本补充')
    return p

def select(papers):
    seen=set(); result=[]
    for p in sorted((rank(p) for p in papers), key=lambda p:(bool(p.get('journal')),p['score']),reverse=True):
        key=re.sub(r'[^a-z0-9]','',p['title'].lower())
        if key not in seen:
            result.append(p);seen.add(key)
    return sorted(result,key=lambda p:p['score'],reverse=True)
