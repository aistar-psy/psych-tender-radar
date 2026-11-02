import unittest
from radar.public_safety import public_project_exclusion

class PublicProjectLinkTests(unittest.TestCase):
    def test_download_only_project_without_public_parent_is_quarantined(self):
        self.assertEqual(public_project_exclusion({'title':'学校心理设备中标明细','sourceUrl':''}),'source_link_pending')
        self.assertEqual(public_project_exclusion({'title':'学校心理设备中标明细','sourceUrl':'https://e.gov.cn/a.pdf?signature=example'}),'source_link_pending')

    def test_real_notice_including_query_routed_homepage_is_publishable(self):
        self.assertIsNone(public_project_exclusion({'title':'学校心理服务采购公告','sourceUrl':'https://e.edu.cn/?noticeId=123'}))
        self.assertIsNone(public_project_exclusion({'title':'学校心理服务采购公告','sourceUrl':'https://e.gov.cn/notice/123.html'}))

    def test_observed_owner_directory_is_not_a_project(self):
        self.assertEqual(public_project_exclusion({'title':'云南省楚雄第一中学-招标信息','sourceUrl':'https://www.bidcenter.com.cn/newssearchyz-30355360.html'}),'source_directory')

    def test_news_conference_is_excluded_but_its_actual_procurement_survives(self):
        url='https://www.jl.gov.cn/szfzt/xwfb/xwfbh/2024/event/index.html'
        self.assertEqual(public_project_exclusion({'title':'2024年吉林省两会新闻发布会第一场','sourceUrl':url}),'non_procurement_news')
        self.assertIsNone(public_project_exclusion({'title':'新闻发布会设备采购招标公告','sourceUrl':'https://e.gov.cn/notice/123.html'}))
