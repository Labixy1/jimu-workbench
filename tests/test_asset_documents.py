import tempfile
import unittest
from pathlib import Path
from domain import Store, Conflict
import library

class AssetDocumentTests(unittest.TestCase):
    def test_create_edit_and_source_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'fixture.sqlite3')
            library.init(store)
            parent=library.category_save(store,{'name':'Project','scope':'materials'})
            child=library.category_save(store,{'name':'Notes','scope':'materials','parent_id':parent['id']})
            doc=library.create_document(store,{'category_id':child['id']})
            self.assertEqual(doc['title'],'未命名文稿')
            self.assertEqual(next(a for a in library.catalog(store) if a['id']==doc['id'])['category_id'],child['id'])
            saved=library.save_document(store,{'id':doc['id'],'revision':1,'title':'Notes','content':'# Updated'})
            self.assertEqual(saved['revision'],2)
            with self.assertRaises(Conflict):
                library.save_document(store,{'id':doc['id'],'revision':1,'title':'Stale','content':'stale'})
            source=store.add_source('Fixture original','Original fixture content')['source']
            copy=library.create_document(store,{'title':'Editable','content':'Edited fixture','source_id':source['id'],'source_content':source['content'],'category_id':child['id']})
            self.assertEqual(copy['body']['source_id'],source['id'])
            self.assertEqual(next(s for s in store.sources() if s['id']==source['id'])['content'],'Original fixture content')
            with self.assertRaises(Conflict):
                library.create_document(store,{'source_id':source['id'],'source_content':'changed'})
            store.db.close()
