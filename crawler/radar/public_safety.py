"""Omit credential-bearing download addresses from public artifacts only."""
import html
import re
from urllib.parse import parse_qsl, urlsplit

PRIVATE_QUERY_KEYS = {
    'accesscode', 'accesstoken', 'token', 'authorization', 'apikey',
    'signature', 'sig', 'ossaccesskeyid', 'googleaccessid', 'keypairid',
}
URL_PATTERN = re.compile(r'https?://[^\s<>"\'，。；]+', re.I)


def protected_url(value):
    try:
        parsed = urlsplit(html.unescape(value))
        if parsed.scheme not in ('http', 'https'):
            return False
        if parsed.username is not None or parsed.password is not None:
            return True
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
            key = re.sub(r'[-_]', '', key).casefold()
            if key in PRIVATE_QUERY_KEYS or key.startswith(('xamz', 'xoss')):
                return True
    except ValueError:
        pass
    return False


def redact_public(value):
    """Keep raw evidence private and make a sanitized copy for publication."""
    if isinstance(value, dict):
        return {k: redact_public(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_public(v) for v in value]
    if isinstance(value, str):
        if URL_PATTERN.fullmatch(value) and protected_url(value):
            return ''
        return URL_PATTERN.sub(lambda m: '[下载地址含访问参数，未公开]' if protected_url(m[0]) else m[0], value)
    return value


def public_project_exclusion(project):
    """A project needs an actual public notice route, not an empty download link."""
    url=project.get('sourceUrl')
    try:
        parsed=urlsplit(url) if isinstance(url,str) else None
        if not parsed or parsed.scheme not in ('http','https') or not parsed.hostname or protected_url(url):
            return 'source_link_pending'
    except ValueError:
        return 'source_link_pending'
    from .candidate_urls import is_listing_url
    if is_listing_url(url): return 'source_directory'
    title=project.get('title') or ''
    if '新闻发布会' in title and not re.search('采购|招标|磋商|竞价|成交|中标',title):
        return 'non_procurement_news'
    return None
