import unittest
from unittest.mock import patch
from radar.discovery import build_plan, discover, normalize_url, load_channels

class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict("os.environ", {"SERPER_API_KEY":""})
        env.start()
        self.addCleanup(env.stop)
    def test_round_robin_and_window_identity(self):
        regions = [str(i) for i in range(32)]
        plan = build_plan(regions, {'a':['心理'], 'b':['教育']}, '2026-09-01', '2026-09-07')
        self.assertEqual(len({p['region'] for p in plan[:16]}), 16)
        self.assertEqual(len(plan), 64)
        self.assertIn('before:2026-09-08', plan[0]['query'])
        self.assertEqual(plan, build_plan(regions, {'a':['心理'], 'b':['教育']}, '2026-09-01', '2026-09-07'))
        self.assertNotEqual(plan[0]['id'], build_plan(regions, {'a':['心理']}, '2026-09-02', '2026-09-07')[0]['id'])
    def test_invalid_window(self):
        with self.assertRaises(ValueError):build_plan(['北京'], {'a':['x']}, '2026-09-07', '2026-09-01')
    def test_url_normalization(self):
        self.assertEqual(normalize_url('HTTPS://EXAMPLE.COM:443/a?id=1&utm_source=x#frag'), 'https://example.com/a?id=1')
        self.assertIsNone(normalize_url('javascript:alert(1)'))
    def test_rss_and_dedup(self):
        body=b'<rss><channel><item><title>A</title><link>https://example.com/a?utm_source=x</link></item><item><link>https://example.com/a#x</link></item></channel></rss>'
        result=discover('query', lambda url: {'body':body, 'status_code':200, 'content_type':'application/rss+xml','url':url})
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(len(result['links']),1)
        self.assertEqual(result['links'][0]['url'],'https://example.com/a')
    def test_block_and_unknown_are_not_empty_success(self):
        for body, code, status in [(b'captcha',200,'blocked'),(b'forbidden',403,'blocked'),(b'<html>oops</html>',200,'parse_error')]:
            result=discover('query',lambda url:{'body':body,'status_code':code,'url':url})
            self.assertEqual(result['status'],status)
            self.assertTrue(result['error'])
    def test_valid_empty_feed(self):
        result=discover('q',lambda url:{'body':b'<rss><channel/></rss>' if 'bing.com' in url else b'<div class="no-results">No results found</div>','status_code':200,'url':url})
        self.assertEqual(result['status'],'empty')
    def test_network_failure(self):
        def fail(url):raise TimeoutError('timed out')
        self.assertEqual(discover('q',fail)['status'],'fetch_error')
    def test_irrelevant_chinese_results_rejected(self):
        rss = b'<rss><channel><item><title>Create Minecraft</title><link>https://example.com/a</link></item></channel></rss>'
        result = discover('上海 心理 招标', lambda url: {'body':rss,'status_code':200})
        self.assertEqual(result['status'], 'irrelevant_results')
        self.assertFalse(result['links'])
        self.assertTrue(result['attempts'])
    def test_duckduckgo_fallback(self):
        def fetch(url):
            if 'bing.com' in url:return {'body':b'captcha','status_code':403}
            return {'body':'<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fnotice">上海学校心理采购公告</a></div>'.encode(), 'status_code':200}
        result=discover('上海 心理 招标', fetch)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['provider'], 'duckduckgo_html')
        self.assertEqual(result['links'][0]['url'], 'https://example.com/notice')
    def test_primary_plan(self):
        p=build_plan(['上海'], {'a':['a','b','c','d','e','f']}, '2026-09-01','2026-09-07')
        self.assertEqual([x['group_index'] for x in p],[0,1])
        self.assertEqual([x['primary'] for x in p],[True,False])
    def test_channels_available(self):
        channels=load_channels()
        self.assertEqual(len(channels),5)
        self.assertTrue(any('一生一档' in word for words in channels.values() for word in words))

if __name__=='__main__':unittest.main()

class SearchPaginationTests(unittest.TestCase):
 def test_bing_reads_page_two_and_stops_on_repeated_page(self):
  calls=[]
  def fetch(url):
   calls.append(url);n=2 if 'first=11' in url or 'first=21' in url else 1
   return {'status_code':200,'body':f'<rss><channel><item><title>学校心理服务采购{n}</title><link>https://a.cn/{n}</link></item></channel></rss>'.encode()}
  r=discover('心理',fetch)
  self.assertEqual(len(r['links']),2)
  self.assertEqual(r['pagination']['stop_reason'],'repeated_page')
  self.assertFalse(r['pagination']['complete'])
