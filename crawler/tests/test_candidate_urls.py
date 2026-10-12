import unittest
from radar.candidate_urls import is_listing_url


class CandidateUrlTests(unittest.TestCase):
    def test_keyword_hotlists_are_not_notices(self):
        for url in (
            'https://www.bidcenter.com.cn/hotlist-1-5206-5d9a96040d5d22a66cd59fe5da1dd410.html',
            'https://www.qianlima.com/hot4200465/',
            'https://m.bidcenter.com.cn/enterprise/szswjqjyj/',
            'https://www.jianyu360.cn/jycms/i_0601/440600_---1.html',
        ):
            with self.subTest(url=url): self.assertTrue(is_listing_url(url))

    def test_hotlist_names_do_not_block_other_hosts_or_real_notice_routes(self):
        for url in (
            'https://example.edu.cn/hot4200465/',
            'https://sxs.qianlima.com/zbcontent-621908232.html',
            'https://www.bidcenter.com.cn/news-444881426-4.html',
            'https://xinjiang.jianyu360.cn/jybx/20261007_26100691082271.html',
        ):
            with self.subTest(url=url): self.assertFalse(is_listing_url(url))

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
