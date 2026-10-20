"""Known result directories are discovery inputs, never individual notices."""
import re
from urllib.parse import urlsplit, parse_qs


def is_listing_url(url):
    try:
        parsed = urlsplit(url)
        host, path = (parsed.hostname or '').lower(), parsed.path.lower()
    except (TypeError, ValueError):
        return False
    if host == 'zfcg.henan.gov.cn' or host.endswith('.zfcg.henan.gov.cn'):
        return bool(re.fullmatch(r'/(?:[a-z]+/)?list[12]/?', path)) or (
            not parsed.query and (path in ('', '/') or bool(re.fullmatch(r'/[a-z]+/?', path))))
    if host in ('sxggzyjy.cn', 'www.sxggzyjy.cn') and path in ('', '/') and not parsed.query:
        return True
    if host == 'bidcenter.com.cn' or host.endswith('.bidcenter.com.cn'):
        return bool(re.match(r'^/(?:zhaobiao/(?:agencies_|areanew_|zbkeyw-)|hotlist-|enterprise/)', path))
    if host == 'qianlima.com' or host.endswith('.qianlima.com'):
        return path.startswith('/gjxx/') or bool(re.fullmatch(r'/hot\d+/?', path))
    if host == 'jianyu360.cn' or host.endswith('.jianyu360.cn'):
        return path.startswith('/jycms/')
    if host == 'ccgp.gov.cn' or host.endswith('.ccgp.gov.cn'):
        return bool(re.search(r'/index(?:_\d+)?\.html?$', path))
    if host == 'hnnkyy.com' or host.endswith('.hnnkyy.com'):
        return parse_qs(parsed.query).get('a') == ['lists']
    return False
