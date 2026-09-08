import unittest
from radar.search_recipes import load_recipes, clauses, match_recipes, build_recipe_plan, seed_plan
class RecipeTests(unittest.TestCase):
 def test_original_recipe_structure(self):
  r=load_recipes();self.assertEqual([x['id'] for x in r['recipes']],list('ABCDEF'))
  self.assertEqual(len(r['families']),8)
  self.assertEqual(len(clauses(r['recipes'][1]['syntax'])),45)
  self.assertEqual(len(clauses(r['recipes'][2]['syntax'])),42)
 def test_boolean_logic_and_field(self):
  self.assertEqual(clauses('(a OR b) AND (c OR d)'),[('a','c'),('a','d'),('b','c'),('b','d')])
  self.assertIn('D',match_recipes('成长指导中心设备购置'))
  self.assertIn('C',match_recipes('智慧校园服务项目','含学生心理预警功能'))
  self.assertNotIn('C',match_recipes('智慧校园采购'))
  self.assertNotIn('A',match_recipes('建设服务','心理健康'))
  self.assertIn('E',match_recipes('12355热线服务合同公告'))
 def test_all_atoms_planned_without_added_terms(self):
  plan=build_recipe_plan([{'id':'a','domains':['a.cn']},{'id':'b','domains':['b.cn']}],'2025-09-09','2026-09-08')
  self.assertEqual([x['source_id'] for x in plan[:2]],['a','b'])
  self.assertEqual({x['recipe_id'] for x in plan},set('ABCDEF'))
  hidden=next(x for x in plan if x['terms']==['舒心小屋'])
  self.assertNotIn('采购',hidden['query']);self.assertNotIn('教育',hidden['query'])
  self.assertIn('before:2026-09-09',hidden['query'])
 def test_seed_queries_are_lossless_supersets_of_every_clause(self):
  atoms=build_recipe_plan([{'id':'a','domains':['a.cn']}],'2025-09-09','2026-09-08')
  seeds=seed_plan(atoms)
  self.assertLess(len(seeds),len(atoms))
  mapped={id:s for s in seeds for id in s['atom_ids']}
  self.assertEqual(set(mapped),{a['id'] for a in atoms})
  for a in atoms:self.assertTrue(any(mapped[a['id']]['keyword'] in term for term in a['terms']))
 def test_word_boundary_false_positive_is_not_psychology(self):
  self.assertEqual(match_recipes('疾病预防控制中心理化所设备采购'),[])
  self.assertIn('A',match_recipes('学校理化生实验室和心理咨询室建设项目'))
