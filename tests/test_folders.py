import tempfile
import unittest
from pathlib import Path
from domain import Store
import library


class FolderTests(unittest.TestCase):
    def test_independent_trees_and_cycle_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'test.sqlite3')
            library.init(store)
            project = library.category_save(store, {'name': 'Project', 'scope': 'materials'})
            child = library.category_save(store, {'name': 'Notes', 'scope': 'materials', 'parent_id': project['id']})
            output = library.category_save(store, {'name': 'Project', 'scope': 'creations'})
            self.assertNotEqual(project['id'], output['id'])
            leaf=library.category_save(store, {'name':'Leaf','scope':'materials','parent_id':child['id']})
            with self.assertRaises(ValueError):
                library.category_save(store, {'name':'Too deep','scope':'materials','parent_id':leaf['id']})
            with self.assertRaises(ValueError):
                library.category_save(store, {**project, 'parent_id': child['id']})
            with self.assertRaises(ValueError):
                library.category_save(store, {'name': 'Invalid', 'scope': 'creations', 'parent_id': project['id']})
            library.category_remove(store, project)
            saved = next(c for c in library.categories(store) if c['id'] == child['id'])
            self.assertEqual(saved['parent_id'], '')
            store.db.close()
