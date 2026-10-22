"""Local Skill contracts and transport checks; no paid model calls."""
import base64
import io
import json
import stat
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import test_api
from domain import Conflict, Store
from engine import OpenCode, Runner, chat_artifact
from test_runner_repair import FixtureEngine
import skill_packages
import task_skills


TEXT = '---\nname: product-research\ndescription: Use when comparing product workflows.\n---\n\n# Product research\n\nRead references/method.md only when comparing flows.\n'


def encoded(value):
    return base64.b64encode(value).decode()


def bundle(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return encoded(output.getvalue())


class SkillPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'db')
        task_skills.init(self.store)

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def save(self, **updates):
        return task_skills.save(self.store, {'skill_md': TEXT, **updates})

    def test_metadata_and_package_roundtrip(self):
        imported = skill_packages.preview('method.zip', bundle([
            ('product-research/SKILL.md', TEXT), ('product-research/references/method.md', 'Compare the actual workflow.'),
            ('product-research/scripts/check.py', 'raise RuntimeError("must not execute")'),
            ('product-research/assets/icon.png', b'\x89PNG\x00test')]))
        saved = self.save(**imported)
        again = skill_packages.preview('export.zip', encoded(skill_packages.export(saved)))
        self.assertEqual(again['skill_md'], TEXT)
        self.assertEqual([r['path'] for r in again['resources']], ['assets/icon.png', 'references/method.md', 'scripts/check.py'])
        self.assertEqual(again['resources'], saved['resources'])

    def test_frontmatter_supports_folded_description_and_preserves_metadata(self):
        text = TEXT.replace('description: Use when comparing product workflows.', 'description: >-\n  Use when comparing\n  product workflows.\nmetadata:\n  owner: local')
        self.assertEqual(skill_packages.parse(text)['description'], 'Use when comparing product workflows.')
        self.assertIn('metadata:\n  owner: local', self.save(skill_md=text)['skill_md'])

    def test_invalid_frontmatter_and_names_are_rejected(self):
        for text in ('# Not a Skill', TEXT.replace('product-research', '../escape'), TEXT.replace('description:', 'purpose:'), TEXT.split('# Product')[0], TEXT.replace('name: product-research', 'name: product-research\nname: duplicate')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                skill_packages.parse(text)

    def test_duplicate_name_does_not_overwrite(self):
        original = self.save()
        with self.assertRaises(Conflict):self.save()
        self.assertEqual(task_skills.get(self.store, original['id'])['revision'], 1)

    def test_edits_preserve_resources_and_reject_stale_revision(self):
        original = self.save(resources=[{'path': 'references/method.md', 'content': encoded(b'Keep me')}])
        edited = self.save(id=original['id'], revision=1, skill_md=TEXT+'\nAdded step.\n')
        self.assertEqual(edited['resources'], original['resources'])
        with self.assertRaises(Conflict):self.save(id=original['id'], revision=1)
        task_skills.init(self.store)
        self.assertEqual(task_skills.get(self.store, original['id'])['skill_md'], edited['skill_md'])

    def test_archived_package_stays_archived_after_init(self):
        original = self.save()
        task_skills.remove(self.store, original)
        task_skills.init(self.store)
        self.assertNotIn(original['id'], [s['id'] for s in task_skills.catalog(self.store)])
        with self.assertRaises(ValueError):task_skills.selected(self.store, [original])

    def test_default_migration_tolerates_editor_trim_but_preserves_user_edits(self):
        name='experience-writing'
        legacy=task_skills.get(self.store,name)
        old='---\nname: experience-writing\ndescription: Old default.\n---\n\n# Old method\nOld method body.\n'
        import hashlib
        with patch.dict(task_skills.PREVIOUS_DEFAULTS,{name:[hashlib.sha256(old.encode()).hexdigest()]}):
            legacy['instructions']=old.rstrip()
            self.store.db.execute('UPDATE managed_skills SET body=? WHERE id=?',(json.dumps(legacy),name));self.store.db.commit()
            task_skills.init(self.store)
            self.assertEqual(task_skills.get(self.store,name)['instructions'],(task_skills.ROOT/name/'SKILL.md').read_text())
            task_skills.save(self.store,{**task_skills.get(self.store,name),'instructions':old+'\nUser-added rule.'})
            task_skills.init(self.store)
            self.assertTrue(task_skills.get(self.store,name)['instructions'].endswith('User-added rule.'))

    def test_catalog_is_metadata_only_and_selected_rules_are_bounded(self):
        skill = self.save(resources=[{'path':'references/method.md','content':encoded(b'resource body')}])
        row = next(s for s in task_skills.catalog(self.store) if s['id']==skill['id'])
        self.assertEqual(row['files'], ['SKILL.md','references/method.md'])
        self.assertNotIn('instructions', row)
        self.assertNotIn('skill_md', row)
        chosen=task_skills.prompt_skills(task_skills.selected(self.store,[skill,skill]))
        self.assertEqual(len(chosen),1)
        self.assertEqual(chosen[0]['instructions'],TEXT)
        self.assertNotIn('resources',chosen[0])

    def test_archive_path_escape_nested_skills_and_duplicates_are_rejected(self):
        for name in ('../secret', '/absolute', 'product-research/../../secret', 'product-research/references/../secret', 'product-research/.env', 'product-research/other/SKILL.md', 'product-research/references\\evil'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                skill_packages.preview('test.zip', bundle([('product-research/SKILL.md',TEXT),(name,'bad')]))
        with self.assertRaises(ValueError):
            skill_packages.preview('test.zip', bundle([('SKILL.md',TEXT),('refs/a','one'),('refs/A','two')]))

    def test_symlink_and_oversized_archive_are_rejected(self):
        link=zipfile.ZipInfo('references/link');link.external_attr=(stat.S_IFLNK|0o777)<<16
        for entries in ([('SKILL.md',TEXT),(link,'/private')], [('SKILL.md',TEXT),('huge.txt','x'*(skill_packages.MAX_BYTES+1))]):
            with self.assertRaises(ValueError):skill_packages.preview('test.zip',bundle(entries))

    def test_runtime_discovers_packages_without_shell_or_external_permissions(self):
        skill=self.save(resources=[{'path':'scripts/check.py','content':encoded(b'never run')}])
        engine=OpenCode('http://127.0.0.1:1','fixture',self.root/'runtime')
        engine.call=lambda *args,**kwargs: None
        engine.configure('fixture',model='fixture',allow_connectors=False,skills=[skill],skill_run='job-test')
        config=json.loads((self.root/'runtime/opencode.json').read_text())
        self.assertEqual(config['skills']['paths'],[str(engine.skill_root)])
        self.assertEqual((engine.skill_root/skill['name']/'SKILL.md').read_text(),TEXT)
        self.assertEqual(config['agent']['workbench']['permission']['skill'],{'*':'deny','product-research':'allow'})
        self.assertFalse(config['agent']['workbench']['tools']['bash'])
        self.assertFalse(config['agent']['workbench']['tools']['write'])
        self.assertTrue(config['agent']['workbench']['tools']['skill'])
        calls=[]
        engine.call=lambda path,body=None,**kwargs: calls.append((path,body)) or {'id':'session'}
        engine.create('workbench',{'providerID':'fixture','modelID':'fixture'})
        rules=calls[-1][1]['permission']
        self.assertTrue(any(r['permission']=='skill' and r['pattern']=='product-research' and r['action']=='allow' for r in rules))
        self.assertFalse(any(r['permission']=='bash' and r['action']=='allow' for r in rules))

    def test_normal_chat_does_not_force_an_artifact(self):
        self.assertEqual(chat_artifact('A normal answer.',self.store,[]),('A normal answer.',None,None))

    def test_board_from_chat_is_a_draft_and_only_saved_explicitly(self):
        value={'type':'board','title':'Test board','content':'A user-requested design, not a factual claim.','diagram':['Task','Draft','Save'],'citations':[]}
        reply='Here is the draft.\n```jimu-artifact\n'+json.dumps(value)+'\n```\n<conversation_title>Test board</conversation_title>'
        engine=FixtureEngine(self.root,[reply])
        job=self.store.create_job(self.store.conversation(),'map-agent',{'kind':'chat','prompt':'Draw this test flow','source_ids':[],'preferences_snapshot':{},'history_snapshot':[]})
        Runner(self.store,engine,{'mode':'model','model':'fixture','base_url':'http://127.0.0.1:1'}).run(job['id'],threading.Event())
        result=self.store.job(job['id'])
        self.assertEqual(result['status'],'review',result['payload'].get('error'))
        self.assertEqual(result['payload']['kind'],'chat')
        self.assertEqual(result['payload']['chat_output'],'board')
        self.assertNotIn('jimu-artifact',result['payload']['answer'])
        self.assertFalse(any(a['kind']=='board' for a in self.store.artifacts()))
        saved=self.store.approve(job['id'])
        self.assertEqual(saved['kind'],'board')
        self.assertEqual(self.store.approve(job['id'])['id'],saved['id'])

    def test_chat_artifact_rejects_invalid_graph_and_invented_citations(self):
        for value in ({'type':'board','title':'Bad','content':'No graph'}, {'type':'document','title':'Bad','content':'Claim','citations':[{'source_id':'invented','quote':'invented quote'}]}):
            with self.assertRaises(ValueError):chat_artifact('```jimu-artifact\n'+json.dumps(value)+'\n```',self.store,[])


class SkillApiTests(unittest.TestCase):
    setUp=test_api.ApiTests.setUp
    tearDown=test_api.ApiTests.tearDown
    request=test_api.ApiTests.request

    def test_import_preview_is_not_an_install(self):
        before=len(task_skills.catalog(self.app.store))
        status,preview=self.request('/api/skills/import-preview',{'filename':'SKILL.md','content':encoded(TEXT.encode())})
        self.assertEqual(status,200)
        self.assertEqual(len(task_skills.catalog(self.app.store)),before)
        status,saved=self.request('/api/skills',preview)
        self.assertEqual(status,200)
        self.assertEqual(self.request('/api/skills/'+saved['id'])[1]['skill_md'],TEXT)
        self.assertNotIn('skill_md',self.request('/api/state')[1]['skills'][-1])

    def test_chat_keeps_routing_and_freezes_both_selected_and_discoverable_versions(self):
        selected=task_skills.get(self.app.store,'board-generation')
        _,job=self.request('/api/jobs',{'kind':'chat','prompt':'What inputs do you need?','skill_refs':[selected]})
        self.assertEqual(job['payload']['kind'],'chat')
        self.assertFalse(job['payload']['output_board'])
        self.assertTrue(all(s['skill_md'].startswith('---\n') for s in job['payload']['skill_catalog_snapshot']))
        task_skills.save(self.app.store,{**selected,'instructions':selected['instructions']+'\nNew instruction.'})
        frozen=self.app.store.job(job['id'])['payload']
        self.assertEqual(frozen['skill_snapshot'][0]['revision'],selected['revision'])
        row=next(s for s in frozen['skill_catalog_snapshot'] if s['id']==selected['id'])
        self.assertEqual(row['revision'],selected['revision'])
        self.assertNotIn('skill_catalog_snapshot',self.request('/api/state')[1]['jobs'][0]['payload'])

    def test_chat_document_edit_and_save_keep_conversation_in_chat(self):
        _,job=self.request('/api/jobs',{'kind':'chat','prompt':'Write a note'})
        page={'title':'Note','summary':'Note','content':'A draft','citations':[]}
        ready=self.app.store.update_job(job['id'],'review',chat_output='document',proposal={'page':page})
        status,edited=self.request('/api/jobs/'+job['id']+'/draft',{'title':'Edited','content':'Edited body','expected_updated':ready['updated']})
        self.assertEqual(status,200)
        self.assertEqual(edited['payload']['kind'],'chat')
        self.assertFalse(any(a['kind']=='wiki' for a in self.app.store.artifacts()))
        status,saved=self.request('/api/jobs/'+job['id']+'/approve',{})
        self.assertEqual(status,200,saved)
        self.assertEqual(saved['body']['content'],'Edited body')
