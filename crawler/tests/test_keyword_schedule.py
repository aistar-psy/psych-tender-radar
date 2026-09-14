import unittest
from radar.search_recipes import build_recipe_plan
from radar.keyword_scan import scheduled_plan

class KeywordScheduleTests(unittest.TestCase):
    def setUp(self):
        self.plan=build_recipe_plan([{'id':str(i),'domains':[f's{i}.example.org']} for i in range(135)],'2025-09-15','2026-09-14')
    def test_limited_budget_reaches_all_recipes_and_sources(self):
        rows=scheduled_plan(self.plan,0)
        self.assertEqual({x['source_id'] for x in rows[:135]},{str(i) for i in range(135)})
        self.assertEqual({x['recipe_id'] for x in rows[:192]},set('ABCDEF'))
        self.assertEqual({x['id'] for x in rows},{x['id'] for x in self.plan})
        self.assertEqual(len(rows),len(self.plan))
    def test_resume_advances_without_modifying_original_queries(self):
        first=scheduled_plan(self.plan,0)
        following=scheduled_plan(self.plan,192)
        self.assertEqual(following[0],first[192])
        self.assertEqual(following[-1],first[191])
