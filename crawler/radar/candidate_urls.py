"""Known result directories are discovery inputs, never individual notices."""
import re
from urllib.parse import urlsplit, parse_qs


def is_listing_url(url):
    try:
        parsed = urlsplit(url)
        host, path = (parsed.hostname or '').lower(), parsed.path.lower()
    except (TypeError, ValueError):
        return False
    if path in ('', '/') and not parsed.query and host in ('www.uwh.edu.cn','www.qhpolice.edu.cn','wbs.wut.edu.cn','xsc.ahwsjkxy.edu.cn','xsc.dgpt.edu.cn'):
        return True
    if host == 'gdpt.edu.cn' or host.endswith('.gdpt.edu.cn'):
        if path == '/main/index/index.html' and not parsed.query: return True
    if host == 'qhpolice.edu.cn' or host.endswith('.qhpolice.edu.cn'):
        if path == '/39/list.htm' and not parsed.query: return True
    if host == 'zfcg.henan.gov.cn' or host.endswith('.zfcg.henan.gov.cn'):
        return bool(re.fullmatch(r'/(?:[a-z]+/)?list[12]/?', path)) or (
            not parsed.query and (path in ('', '/') or bool(re.fullmatch(r'/[a-z]+/?', path))))
    if host in ('sxggzyjy.cn', 'www.sxggzyjy.cn') and path in ('', '/') and not parsed.query:
        return True
    if host == 'bidcenter.com.cn' or host.endswith('.bidcenter.com.cn'):
        return bool(re.match(r'^/(?:zhaobiao/(?:agencies_|areanew_|zbkeyw-)|hotlist-|enterprise/|newssearch(?:yz|zb)-)', path))
    if host == 'qianlima.com' or host.endswith('.qianlima.com'):
        return path.startswith('/gjxx/') or bool(re.fullmatch(r'/hot\d+/?', path))
    if host == 'jianyu360.cn' or host.endswith('.jianyu360.cn'):
        return path.startswith('/jycms/')
    if host == 'jszhaobiao.cn' or host.endswith('.jszhaobiao.cn'):
        return bool(re.fullmatch(r'/s\d+/?', path))
    if host == 'zhaobiao.cn' or host.endswith('.zhaobiao.cn'):
        return bool(re.fullmatch(r'/ts_i_[a-z0-9_]+\.html?', path)) or (host == 's.zhaobiao.cn' and path.startswith('/search'))
    if host == 'ccgp.gov.cn' or host.endswith('.ccgp.gov.cn'):
        return bool(re.search(r'/index(?:_\d+)?\.html?$', path))
    if host == 'hnnkyy.com' or host.endswith('.hnnkyy.com'):
        return parse_qs(parsed.query).get('a') == ['lists']
    return False
