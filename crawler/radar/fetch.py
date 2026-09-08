"""Bounded HTTP reads. Failed reads never masquerade as empty results."""
import hashlib
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import requests

class FetchError(RuntimeError):
    def __init__(self, kind, message, url=''):
        super().__init__(message)
        self.kind, self.url = kind, url

def canonical_url(url):
    p = urlsplit(url.strip())
    query = [(k,v) for k,v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in ('spm','from')]
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path or '/',urlencode(query),''))

class Fetcher:
    def __init__(self, interval=1.0, timeout=15, max_bytes=20*1024*1024, retries=1):
        self.interval, self.timeout, self.max_bytes, self.retries = interval, timeout, max_bytes, retries
        self.last = {}
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'PsychTenderRadar/0.1 (public procurement research; low-rate)'
    def __call__(self, url):
        url = canonical_url(url)
        if urlsplit(url).scheme not in ('http','https'):
            raise FetchError('invalid_url','Only HTTP(S) URLs are supported',url)
        host = urlsplit(url).netloc
        for attempt in range(self.retries+1):
            time.sleep(max(0,self.interval-(time.monotonic()-self.last.get(host,0))))
            self.last[host] = time.monotonic()
            try:
                # Loopback integration sources must not be routed through a machine-wide proxy.
                local = urlsplit(url).hostname in ('127.0.0.1','localhost','::1')
                proxies = {'http':'','https':'','all':''} if local else None
                with self.session.get(url,timeout=self.timeout,stream=True,proxies=proxies) as r:
                    if r.status_code in (401,403,429):
                        raise FetchError('blocked',f'HTTP {r.status_code}',url)
                    if r.status_code >= 400:
                        raise FetchError('http_error',f'HTTP {r.status_code}',url)
                    try: declared = int(r.headers.get('Content-Length','0'))
                    except ValueError: declared = 0
                    if declared > self.max_bytes:
                        raise FetchError('too_large',f'Content-Length exceeds {self.max_bytes}',url)
                    chunks, size = [],0
                    for chunk in r.iter_content(65536):
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise FetchError('too_large',f'Response exceeds {self.max_bytes}',url)
                        chunks.append(chunk)
                    body = b''.join(chunks)
                    ct = r.headers.get('Content-Type','')
                    if 'html' in ct:
                        start = body[:16000].decode('utf-8','ignore').lower()
                        # Strong challenge signals only: a normal procurement page may mention verification.
                        if any(s in start for s in ('cf-chl-','verify you are human','访问过于频繁','人机验证','acw_sc__v2')):
                            raise FetchError('blocked','HTML challenge page',url)
                    return {'body':body,'content_type':ct,'url':r.url,'status_code':r.status_code,
                            'sha256':hashlib.sha256(body).hexdigest()}
            except FetchError:
                raise
            except requests.RequestException as exc:
                if attempt==self.retries:
                    raise FetchError('network_error',str(exc)[:500],url) from exc
                time.sleep(min(2,attempt+1))
        raise FetchError('network_error','No response',url)

def save_evidence(result, directory):
    directory = Path(directory); directory.mkdir(parents=True,exist_ok=True)
    digest = result.get('sha256') or hashlib.sha256(result['body']).hexdigest()
    path = directory / (digest+'.bin')
    if not path.exists(): path.write_bytes(result['body'])
    return {'sha256':digest,'path':str(path),'url':result['url'],'content_type':result['content_type']}
