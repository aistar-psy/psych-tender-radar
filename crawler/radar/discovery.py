"""Bounded public search discovery, not an exhaustive procurement crawler.

Search date terms are hints only; downstream publication-date filtering is required.
The caller persists its plan cursor; successive slices retain region round-robin order.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from xml.etree import ElementTree

CONFIG = Path(__file__).resolve().parent.parent / 'config'


def load_channels(path=None):
    """Load portable channel terms derived from the supplied V1.3 vocabulary."""
    return json.loads(Path(path or CONFIG / 'channels.json').read_text(encoding='utf-8'))


def build_plan(regions: list[str], channels: dict[str, list[str]], start: str, end: str) -> list[dict]:
    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError('start must be on or before end')
    exclusive_end = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    regions = list(dict.fromkeys(regions))
    # Split large dictionaries into bounded OR groups; every group visits all regions.
    groups = {name: [terms[i:i+5] for i in range(0, len(terms), 5)] for name, terms in channels.items()}
    plan = []
    for group_index in range(max((len(g) for g in groups.values()), default=0)):
        for channel, batches in groups.items():
            if group_index >= len(batches):
                continue
            terms = batches[group_index]
            for region in regions:
                query = f'{region} (' + ' OR '.join('"'+term.replace('"','')+'"' for term in terms) + f') after:{start} before:{exclusive_end}'
                identity = json.dumps([region,channel,query,start,end],ensure_ascii=False,separators=(',',':'))
                plan.append({'id':hashlib.sha256(identity.encode()).hexdigest()[:24], 'region':region, 'channel':channel, 'query':query, 'group_index':group_index, 'primary':group_index == 0})
    return plan


def normalize_url(url: str):
    """Remove fragments and known tracking keys, retain business identifiers."""
    try:
        parts = urlsplit(url.strip())
        if parts.scheme.lower() not in ('http','https') or not parts.hostname or parts.username or parts.password:
            return None
        scheme = parts.scheme.lower()
        host = parts.hostname.lower()
        if ':' in host:
            host = '[' + host + ']'
        port = parts.port
        if port and not (scheme == 'http' and port == 80 or scheme == 'https' and port == 443):
            host += ':' + str(port)
        params = [(k,v) for k,v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith('utm_') and k.lower() not in ('gclid','fbclid')]
        return urlunsplit((scheme,host,parts.path or '/',urlencode(params),''))
    except (ValueError,AttributeError):
        return None


def _bing_rss(query: str, fetch_callable, page_number=1) -> dict:
    """Read a public Bing RSS response; errors/captcha never mean zero results.

    Returns links as dictionaries containing url/text/kind=page. An individual feed page is fetched; caller checks repeated pages. Search indexing, date hints and recall are not guaranteed.
    """
    endpoint = 'https://www.bing.com/search?' + urlencode({'q':query,'format':'rss',**({'first':(page_number-1)*10+1} if page_number>1 else {})})
    def result(status, error='', links=None):
        return {'status':status,'links':links or [],'error':error}
    try:
        response = fetch_callable(endpoint)
    except Exception as exc:
        return result('fetch_error', f'{type(exc).__name__}: {exc}')
    code = response.get('status_code', 0)
    body = response.get('body', b'')
    if isinstance(body, str):
        body = body.encode('utf-8')
    snippet = body[:200000].decode('utf-8',errors='replace').lower()
    if code in (401,403,429) or any(marker in snippet for marker in ('captcha','人机验证','访问验证','verify you are human','unusual traffic','access denied')):
        return result('blocked',f'Public search blocked or challenged (HTTP {code}); coverage unverified')
    if code != 200:
        return result('fetch_error', f'HTTP {code}: {response.get("error", "search request failed")}')
    try:
        root = ElementTree.fromstring(body)
        if root.tag != 'rss' or root.find('channel') is None:
            return result('parse_error','Expected RSS channel; HTML/unknown response is not proof of no results')
        links, seen = [], set()
        items = root.findall('./channel/item')
        for item in items:
            url = normalize_url(item.findtext('link',''))
            if url and url not in seen:
                seen.add(url)
                links.append({'url':url,'text':item.findtext('title',''),'snippet':item.findtext('description',''),'kind':'page'})
        if items and not links:
            return result('parse_error','Feed contained items but no usable HTTP links')
        return result('ok' if links else 'empty', links=links)
    except ElementTree.ParseError as exc:
        return result('parse_error',f'Invalid RSS response: {exc}')


class _DuckResults(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and 'result__a' in attrs.get('class', '').split():
            href = attrs.get('href', '')
            if href.startswith('//'):
                href = 'https:' + href
            parts = urlsplit(href)
            if parts.hostname and parts.hostname.endswith('duckduckgo.com'):
                href = dict(parse_qsl(parts.query)).get('uddg', '')
            url = normalize_url(href)
            self.current = {'url':url,'text':'','kind':'page'} if url else None

    def handle_data(self, data):
        if self.current is not None:
            self.current['text'] += data

    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            self.links.append(self.current)
            self.current = None


def _duckduckgo(query, fetch_callable):
    endpoint = 'https://html.duckduckgo.com/html/?' + urlencode({'q':query})
    try:
        response = fetch_callable(endpoint)
        body = response.get('body', b'')
        text = body.decode('utf-8',errors='replace') if isinstance(body, bytes) else body
        code = response.get('status_code', 0)
        if code in (202,401,403,429) or any(s in text.lower() for s in ('anomaly.js','challenge-form','captcha','verify you are human')):
            return {'status':'blocked','links':[],'error':f'DuckDuckGo challenge or block (HTTP {code})'}
        if code != 200:
            return {'status':'fetch_error','links':[],'error':f'DuckDuckGo HTTP {code}'}
        parser = _DuckResults()
        parser.feed(text)
        links = list({x['url']:x for x in parser.links}.values())
        if links:
            return {'status':'ok','links':links,'error':''}
        if 'no-results' in text or 'No results found' in text:
            return {'status':'empty','links':[],'error':''}
        return {'status':'parse_error','links':[],'error':'Unrecognized DuckDuckGo response; not a verified empty result'}
    except Exception as exc:
        return {'status':'fetch_error','links':[],'error':f'{type(exc).__name__}: {exc}'}


def _serper(query, api_key):
    """Optional official Serper JSON endpoint; never expose the configured key."""
    request = Request('https://google.serper.dev/search', data=json.dumps({'q':query,'gl':'cn','hl':'zh-cn','num':10}).encode(), headers={'X-API-KEY':api_key,'Content-Type':'application/json'}, method='POST')
    try:
        with urlopen(request, timeout=15) as response:
            data = json.loads(response.read(2_000_000))
        if not isinstance(data.get('organic'), list):
            return {'status':'parse_error','links':[],'error':'Serper response missing organic array'}
        links = []
        for item in data['organic']:
            url = normalize_url(item.get('link',''))
            if url:
                links.append({'url':url,'text':item.get('title',''),'snippet':item.get('snippet',''),'kind':'page'})
        return {'status':'ok' if links else 'empty','links':list({x['url']:x for x in links}.values()),'error':''}
    except Exception as exc:
        return {'status':'fetch_error','links':[],'error':f'Serper {type(exc).__name__}; inspect network/account configuration'}


def _relevance(query, result):
    if result['status'] != 'ok' or not re.search('[\u4e00-\u9fff]',query):
        return result
    # A minimum relevance gate: candidates still require document-level review.
    terms = ('心理','心育','学校','校园','学生','采购','招标','教育','情绪','心灵','成长','辅导','生物反馈','抑郁','焦虑','润心')
    links = [x for x in result['links'] if any(term in (x.get('text','')+' '+x.get('snippet','')) for term in terms)]
    if not links:
        return {'status':'irrelevant_results','links':[],'error':'Search returned no Chinese procurement/mental-health/education relevance; engine query handling unverified'}
    return dict(result, links=links)


def discover(query: str, fetch_callable, max_pages=3) -> dict:
    """Bing RSS -> DuckDuckGo HTML fallback, optional SERPER_API_KEY last.

    Public engine challenges and irrelevant result sets are recorded in attempts.
    A successful search is only a candidate set, not exhaustive/date-verified coverage.
    Serper (if explicitly configured) uses its official POST API with a 15s timeout.
    """
    attempts = []
    engines = [('bing_rss', lambda: _bing_rss(query, fetch_callable)), ('duckduckgo_html', lambda: _duckduckgo(query, fetch_callable))]
    key = os.environ.get('SERPER_API_KEY')
    if key:
        engines.append(('serper_api', lambda: _serper(query,key)))
    failures = []
    for provider, call in engines:
        result = _relevance(query, call())
        attempts.append({'provider':provider,'status':result['status'],'error':result['error'],'link_count':len(result['links'])})
        if result['status'] == 'ok':
            return _paginate_index(query,result,provider,attempts,fetch_callable,max_pages)
        failures.append(result)
    # A recognized empty response cannot hide another engine's challenge/error.
    chosen = next((r for r in failures if r['status'] == 'irrelevant_results'), None)
    if chosen is None:
        chosen = next((r for r in failures if r['status'] not in ('empty',)), failures[0])
    return dict(chosen, provider='none', attempts=attempts)


def _paginate_index(query,first,provider,attempts,fetch,max_pages):
    links={x['url']:x for x in first['links']};seen={tuple(links)}
    pages=[{'page':1,'status':first['status'],'links':len(links)}];stop='adapter_has_no_pagination'
    if provider=='bing_rss':
        stop='page_budget'
        for page in range(2,max_pages+1):
            r=_relevance(query,_bing_rss(query,fetch,page))
            pages.append({'page':page,'status':r['status'],'links':len(r['links']),'error':r.get('error','')})
            if r['status']!='ok':stop='empty_feed' if r['status']=='empty' else 'page_failed';break
            marker=tuple(x['url'] for x in r['links'])
            if marker in seen:stop='repeated_page';break
            seen.add(marker)
            for x in r['links']:links.setdefault(x['url'],x)
    return dict(first,links=list(links.values()),provider=provider,attempts=attempts,pagination={'pages':pages,'stop_reason':stop,'complete':False,'limitation':'站外索引分页不等于源网站全量；重复页或空索引不能证明无公告'})
