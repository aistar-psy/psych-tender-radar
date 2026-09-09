"""Retry queues and truthful public acquisition states."""
import json
from pathlib import Path
from datetime import datetime
from .fetch import canonical_url


def recovery_queue(data):
    start, end = data['yearRange']['start'], data['yearRange']['end']
    rows = {}
    for p in data.get('archiveProjects', []):
        dates = [p.get('publishedAt')] + [e.get('publishedAt') for e in p.get('events', [])]
        if p.get('sourceQuality') == '正文已取得' or not any(start <= str(d)[:10] <= end for d in dates if d):
            continue
        url = canonical_url(p['sourceUrl'])
        rows.setdefault(url, {'url': url, 'title': p['title'], 'published_at': p.get('publishedAt'), 'kind': 'document'})
    return list(rows.values())


def acquisition_state(receipt, task, body_obtained=False):
    def result(code, label, reason):
        return {'code': code, 'label': label, 'reason': reason, 'attemptedAt': receipt.get('read_at'),
                'method': receipt.get('provider'), 'httpStatus': receipt.get('status_code')}
    if body_obtained:
        return result('body_obtained', '正文已取得', '已保存并解析公告正文或公开附件')
    if task.get('status') == 'content_unconfirmed' and receipt.get('status') == 'ok':
        return result('content_unavailable', '正文解析待补', '网页响应已取得，但正文、动态内容、会员可见信息或附件仍未完整读取')
    error = str(receipt.get('error_type', '')) + ' ' + str(receipt.get('error', ''))
    if 'challenge' in error or 'verification' in error:
        return result('verification_required', '验证页面待处理', '普通浏览器仍显示访问验证，尚未取得公告正文')
    if receipt.get('status') == 'failed':
        if any(s in error for s in ('SSL', 'Connection', 'Timeout', 'network_error', 'ERR_CONNECTION', 'ERR_CERT')):
            return result('connection_failed', '连接失败', 'HTTPS 证书、连接中断或超时；等待后续重试或发布源补抓')
        return result('access_failed', '页面访问失败', '页面返回访问错误或浏览器读取失败；不能据此判断没有项目')
    if receipt.get('status') == 'ok' or task.get('status') == 'content_unconfirmed':
        return result('content_unavailable', '正文解析待补', '网页响应已取得，但尚未识别有效采购正文或公开附件')
    if task.get('status') in ('blocked', 'http_error', 'network_error'):
        return result('access_failed', '页面访问失败', '历史读取失败，尚无成功的正文补抓记录')
    return result('not_attempted', '待抓取正文', '尚无实际正文读取记录，仅有搜索线索')


def latest_receipts(root):
    latest = {}
    def stamp(row):
        try: return datetime.fromisoformat(row.get('read_at', '').replace('Z', '+00:00')).timestamp()
        except (TypeError, ValueError): return 0
    for folder in ('public-downloads', 'cloud-downloads'):
        for f in (Path(root) / 'data' / folder).glob('*/manifest.json'):
            rows = json.loads(f.read_text())
            if isinstance(rows, dict): rows = rows.get('results', [])
            for row in rows:
                if not row.get('url'): continue
                u = canonical_url(row['url'])
                if u not in latest or stamp(row) > stamp(latest[u]): latest[u] = row
    return latest
