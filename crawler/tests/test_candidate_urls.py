import unittest
from radar.candidate_urls import is_listing_url


class CandidateUrlTests(unittest.TestCase):
    def test_known_aggregate_and_official_directories(self):
        for url in (
            'https://www.bidcenter.com.cn/zhaobiao/agencies_1141_360803_0/',
            'https://m.bidcenter.com.cn/zhaobiao/zbkeyw-65905-0-2.html',
            'https://www.qianlima.com/gjxx/27509_2703_0',
            'https://www.ccgp.gov.cn/cggg/zygg/gkzb/index_3.htm',
            'https://www.hnnkyy.com/index.php?m=content&c=index&a=lists&catid=750',
        ):
            with self.subTest(url=url): self.assertTrue(is_listing_url(url))

    def test_real_announcements_and_query_routed_notices_survive(self):
        for url in (
            'https://www.bidcenter.com.cn/news-308232188-1.html',
            'https://www.qianlima.com/bid-630696332.html',
            'https://www.ccgp.gov.cn/cggg/zygg/gkzb/202609/t20260921_1.htm',
            'https://www.hnnkyy.com/index.php?a=show&c=index&catid=744&id=8764&m=content',
            'https://example.edu.cn/zbcontent/123.html',
        ):
            with self.subTest(url=url): self.assertFalse(is_listing_url(url))
