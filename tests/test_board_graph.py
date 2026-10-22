"""Explicit local fixtures: graph semantics and layout, not model quality."""
import copy
import tempfile
import unittest
from pathlib import Path

import boards
import library
from domain import Store
from wiki import sync_wiki


def fixture_graph():
    return {'groups':[{'id':'user','label':'User'},{'id':'agent','label':'Agent'},{'id':'output','label':'Output'}],
            'nodes':[{'id':'input','label':'Select material','group':'user','row':0},
                     {'id':'read','label':'Read evidence','detail':'Only selected sources','group':'agent','row':0},
                     {'id':'check','label':'Evidence sufficient?','group':'agent','row':1,'kind':'decision'},
                     {'id':'ask','label':'Request clarification','group':'user','row':1},
                     {'id':'draft','label':'Create draft','group':'output','row':2},
                     {'id':'edit','label':'Edit and save','group':'user','row':2}],
            'edges':[{'from':'input','to':'read'}, {'from':'read','to':'check'},
                     {'from':'check','to':'ask','label':'No','kind':'feedback'},
                     {'from':'ask','to':'read','label':'Supplement','kind':'feedback'},
                     {'from':'check','to':'draft','label':'Yes'},
                     {'from':'draft','to':'edit','label':'Preview'},
                     {'from':'edit','to':'input','label':'Reuse','kind':'reference'}]}


class BoardGraphTests(unittest.TestCase):
    def test_branch_feedback_and_safe_scene(self):
        graph=boards.validate_graph(fixture_graph());result=boards.graph_scene(graph,'Fixture graph')
        nodes=[e for e in result['elements'] if e['id'].startswith('node_')]
        self.assertEqual(len(nodes),6)
        arrows=[e for e in result['elements'] if e['type']=='arrow']
        self.assertEqual(len(arrows),7)
        self.assertTrue(any(e['type']=='diamond' for e in result['elements']))
        self.assertTrue(any(e['strokeStyle']=='dashed' for e in arrows))
        for arrow in arrows:
            points=[(arrow['x']+x,arrow['y']+y) for x,y in arrow['points']]
            for (x,y),(u,v) in zip(points,points[1:]):
                self.assertTrue(x==u or y==v)
                for node in nodes:
                    l,t=node['x'],node['y'];r,b=l+node['width'],t+node['height']
                    if x==u:self.assertFalse(l<x<r and max(min(y,v),t)<min(max(y,v),b))
                    else:self.assertFalse(t<y<b and max(min(x,u),l)<min(max(x,u),r))
        self.assertEqual(boards.scene(result),result)

    def test_duplicate_missing_overlap_and_oversize_rejected(self):
        mutations=[lambda g:g['nodes'].append(copy.deepcopy(g['nodes'][0])),
                   lambda g:g['edges'].append({'from':'input','to':'missing'}),
                   lambda g:g['nodes'][1].update(group='missing'),
                   lambda g:g['nodes'][2].update(row=0),
                   lambda g:g['nodes'][1].update(row=True),
                   lambda g:g['nodes'][1].update(label='x'*37),
                   lambda g:g['groups'].append({'id':'empty','label':'Empty'}),
                   lambda g:g['nodes'].append({'id':'isolate','label':'No connection','group':'user','row':3})]
        for mutate in mutations:
            graph=fixture_graph();mutate(graph)
            with self.subTest(graph=graph),self.assertRaises(ValueError):boards.validate_graph(graph)

    def test_graph_survives_approval_edit_versions_and_export(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);store=Store(root/'db');library.init(store)
            source=store.add_source('Fixture evidence','Only selected material is read; every saved output requires user confirmation.')['source']
            page={'title':'Fixture graph','summary':'Fixture','content':'Read, verify, edit, save.','tags':[],'links':[],
                  'citations':[{'source_id':source['id'],'quote':source['content']}],'diagram':[],'graph':fixture_graph()}
            job=store.create_job(store.conversation(),'map-agent',{'kind':'wiki','source_ids':[source['id']],
                                  'prompt':'Fixture graph','proposal':{'page':page},'output_board':True})
            store.update_job(job['id'],'review')
            self.assertFalse(any(a['kind']=='board' for a in store.artifacts()))
            board=store.approve(job['id'],{'category_id':'learning'})
            self.assertEqual(board['body']['generated_graph'],boards.validate_graph(page['graph']))
            self.assertEqual(board['body']['citations'],page['citations'])
            self.assertEqual(store.approve(job['id'])['id'],board['id'])
            changed=boards.save(store,{**board,'title':'Edited fixture','scene':board['body']['scene']})
            self.assertEqual(changed['body']['generated_graph'],board['body']['generated_graph'])
            edited=fixture_graph();edited['nodes'][0]['label']='User-selected evidence'
            changed=boards.save(store,{**changed,'scene':boards.graph_scene(edited),'graph':edited,'notes':'Manually revised fixture.'})
            self.assertEqual(changed['body']['generated_graph'],board['body']['generated_graph'])
            self.assertEqual(changed['body']['edited_graph'],boards.validate_graph(edited))
            self.assertEqual(changed['body']['notes'],'Manually revised fixture.')
            wiki=store.save_wiki(page);revised=store.save_wiki({k:v for k,v in page.items() if k!='graph'},wiki['id'],1)
            self.assertEqual(revised['body']['graph'],wiki['body']['graph'])
            directory=sync_wiki(root,store)
            self.assertIn('"edges"',(directory/(wiki['id']+'.md')).read_text())
            linked=boards.from_wiki(store,{'id':wiki['id'],'revision':2})
            self.assertEqual(linked['body']['generated_graph'],wiki['body']['graph'])
            store.db.close()
