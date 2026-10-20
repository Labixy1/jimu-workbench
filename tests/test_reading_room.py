import tempfile
import unittest
from pathlib import Path
from domain import Store
import library
import reading_room

class ReadingRoomTests(unittest.TestCase):
    def test_asset_favorites_focus_and_issue_persistence(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fixture.sqlite3'
            store=Store(path);library.init(store);reading_room.init(store)
            doc=library.create_document(store,{'title':'Fixture','content':'# Fixture'})
            reading_room.favorite(store,{'id':doc['id']})
            self.assertEqual(reading_room.state(store)['favorites'],[doc['id']])
            other=library.create_document(store,{'title':'Second fixture','content':'# Second'})
            reading_room.favorite(store,{'id':other['id']})
            reading_room.favorite_order(store,{'ids':[other['id'],doc['id']]})
            self.assertEqual(reading_room.state(store)['favorites'],[other['id'],doc['id']])
            reading_room.favorite(store,{'id':other['id'],'remove':True})
            reading_room.favorite(store,{'id':doc['id'],'remove':True})
            self.assertFalse(reading_room.state(store)['favorites'])
            self.assertFalse(store.artifact(doc['id'])['archived'])
            focus=reading_room.focus_save(store,{'name':'Fixture account','kind':'公众号','url':'https://example.com'},lambda url:None)
            self.assertEqual(len(reading_room.state(store)['focus']),1)
            reading_room.focus_remove(store,focus)
            reading_room.snapshot(store,[{'title':'Fixture article','url':'https://example.com','excerpt':'Fixture'}])
            store.db.close();store=Store(path);library.init(store);reading_room.init(store)
            self.assertEqual(reading_room.state(store)['issues'][0]['body']['news'][0]['title'],'Fixture article')
            self.assertEqual(len(reading_room.state(store)['focus']),0)
            store.db.close()
