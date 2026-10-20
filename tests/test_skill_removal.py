import tempfile
import unittest
from pathlib import Path
from domain import Store, Conflict
import task_skills


class SkillRemovalTests(unittest.TestCase):
    def test_deleted_builtin_stays_deleted_after_restart(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(Path(root) / 'test.sqlite3')
            task_skills.init(store)
            skill = task_skills.get(store, 'knowledge-compilation')
            with self.assertRaises(Conflict):
                task_skills.remove(store, {'id': skill['id'], 'revision': 0})
            task_skills.remove(store, skill)
            task_skills.init(store)
            self.assertFalse(any(s['id'] == skill['id'] for s in task_skills.all_skills(store)))
            self.assertIsNone(task_skills.task_method('wiki', store))
            with self.assertRaises(ValueError):
                task_skills.selected(store, [skill])
            custom = task_skills.save(store, {'title': 'Test', 'description': 'Test method', 'instructions': 'Test rules'})
            task_skills.remove(store, custom)
            self.assertFalse(any(s['id'] == custom['id'] for s in task_skills.all_skills(store)))
