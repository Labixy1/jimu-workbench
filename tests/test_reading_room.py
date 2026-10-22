import tempfile
import unittest
from pathlib import Path
from domain import Store
import library
import reading_room
from unittest.mock import patch
from datetime import datetime, timezone

class ReadingRoomTests(unittest.TestCase):
    def test_focus_description_migrates_edits_and_keeps_order(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fixture.sqlite3'
            store=Store(path);library.init(store)
            store.db.execute('CREATE TABLE reading_focus(id TEXT PRIMARY KEY,name TEXT,kind TEXT,url TEXT)')
            store.db.execute('INSERT INTO reading_focus VALUES(?,?,?,?)',('legacy','Legacy','官网','https://example.com'))
            store.db.commit();reading_room.init(store)
            self.assertEqual(reading_room.state(store)['focus'][0]['description'],'')
            first={'id':'legacy','name':'Legacy','kind':'官网','url':'https://example.com'}
            second=reading_room.focus_save(store,{'name':'Second','kind':'公众号','url':'https://example.org','description':'  Original source notes  '},lambda _:None)
            reading_room.focus_save(store,{**first,'description':'Product updates'},lambda _:None)
            reading_room.focus_save(store,first,lambda _:None)
            focus=reading_room.state(store)['focus']
            self.assertEqual([item['id'] for item in focus],['legacy',second['id']])
            self.assertEqual([item['description'] for item in focus],['Product updates','Original source notes'])
            for invalid in (None,160*'x'+'x',[]):
                with self.assertRaises(ValueError):reading_room.focus_save(store,{**first,'description':invalid},lambda _:None)
            store.db.close();store=Store(path);reading_room.init(store)
            self.assertEqual(reading_room.state(store)['focus'][0]['description'],'Product updates')
            reading_room.focus_save(store,{**first,'description':''},lambda _:None)
            self.assertEqual(reading_room.state(store)['focus'][0]['description'],'')
            store.db.close()

    def test_week_dedupes_cross_posted_titles_and_bounds_one_feed(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'fixture.sqlite3');library.init(store);reading_room.init(store)
            date=datetime.now(timezone.utc).isoformat()
            items=[{'id':'fixture_'+str(i),'title':'Fixture '+str(i),'published_at':date,'feed_url':'https://example.com/rss',
                    'source_name':'Example' if i<3 else ''} for i in range(12)]
            items.append({**items[0],'id':'repost','feed_url':'https://example.org/rss'})
            reading_room.snapshot(store,items)
            news=reading_room.state(store)['issues'][0]['body']['news']
            self.assertEqual(len(news),8)
            self.assertEqual(len({n['title'] for n in news}),8)
            store.db.close()

    def test_three_weeks_use_publication_not_collection_date(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'fixture.sqlite3');library.init(store);reading_room.init(store)
            news=[{'id':'fixture_'+str(i),'title':'Fixture '+str(i),'url':'https://example.com/'+str(i),'excerpt':'Fixture excerpt',
                   'published_at':date,'fetched_at':'2026-10-21T08:00:00Z'} for i,date in enumerate(
                      ['2026-10-20T00:00:00Z','2026-10-15T00:00:00Z','2026-10-08T00:00:00Z'])]
            with patch('reading_room.datetime') as clock:
                clock.now.return_value=datetime(2026,10,21,8,tzinfo=timezone.utc)
                clock.fromisoformat.side_effect=datetime.fromisoformat
                result=reading_room.snapshot(store,news,weeks=3)
                reading_room.snapshot(store,news,weeks=3)
            self.assertEqual(len(result['issues']),3)
            self.assertEqual([i['period_start'] for i in result['issues']],['2026-10-19','2026-10-12','2026-10-05'])
            self.assertEqual([i['count'] for i in result['issues']],[1,1,1])
            self.assertEqual(store.db.execute('SELECT count(*) FROM reading_issue_versions').fetchone()[0],3)
            self.assertEqual(len(reading_room.state(store)['issues']),3)
            store.db.close()

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
