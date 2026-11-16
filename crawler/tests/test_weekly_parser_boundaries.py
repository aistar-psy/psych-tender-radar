import unittest
from radar.analysis import analyze_document
from radar.candidate_urls import is_listing_url
from radar.documents import parse_document

class WeeklyParserTests(unittest.TestCase):
    def test_jianyu_section_page_is_not_a_notice(self):
        self.assertTrue(is_listing_url('https://henan.jianyu360.cn/xzbg_14/'))
        self.assertFalse(is_listing_url('https://henan.jianyu360.cn/jybx/20261116_261115100789052.html'))

    def test_explicit_hidden_content_banner_demotes_long_summary(self):
        raw = ('<article><h1>某大学心理服务采购公告</h1><p>项目概况：' + '服务期间提供心理咨询。' * 175 +
               '</p><p>页面中****为隐藏内容，只有登录才能查看。</p></article>')
        page = parse_document(raw.encode(), 'https://example.org/notice.html')
        self.assertEqual(page['content_status'], 'unavailable')
        clear = parse_document(raw.replace('页面中****为隐藏内容，只有登录才能查看。', '采购联系人：****').encode(), 'https://example.org/notice.html')
        self.assertEqual(clear['content_status'], 'available')

    def test_affiliated_hospital_medical_package_is_other_psychology(self):
        notice = {'title': '某大学附属医院肝胆病区医疗设备购置公开招标公告', 'text': '标项名称：包十：心理健康管理系统'}
        analysis = analyze_document(notice, 'https://example.org/notice.html', '2026-11-16T09:00:00+08:00')
        self.assertEqual(analysis['category'], '其他心理')
        notice['title'] = '某大学附属医院面向中小学生心理健康教育服务采购公告'
        analysis = analyze_document(notice, 'https://example.org/notice.html', '2026-11-16T09:00:00+08:00')
        self.assertEqual(analysis['category'], '教育核心')

if __name__ == '__main__':
    unittest.main()
