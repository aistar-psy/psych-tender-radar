import json
from pathlib import Path
import tempfile
import unittest
from radar.sop_export import export

class OfflineSopTests(unittest.TestCase):
    def test_cache_busted_assets_are_inlined_on_every_export(self):
        import radar.sop_export as module
        source = module.ROOT
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('config', 'publish', 'docs'):
                (root / name).mkdir()
            for name in ('search_recipes.json', 'sop.json', 'vocabulary_migration.json'):
                (root / 'config' / name).write_bytes((source / 'config' / name).read_bytes())
            public = root / 'publish'
            (public / 'data.js').write_text('window.RADAR_DATA = {"archiveProjects":[]};')
            for name in ('sop.css', 'sop-state.js', 'sop.js'):
                (public / name).write_bytes((source / 'publish' / name).read_bytes())
            html = (source / 'publish/sop.html').read_text()
            import re
            html = re.sub(r'sop-data.js\?v=[^"]+', 'sop-data.js?v=20261123-weekly', html)
            (public / 'sop.html').write_text(html)
            export(root, public)
            offline = (public / 'sop-offline.html').read_text()
            self.assertFalse('<script src=' in offline)
            self.assertFalse('<link rel="stylesheet"' in offline)
            self.assertIn('window.RADAR_SOP', offline)

if __name__ == '__main__':
    unittest.main()
