import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import library
from news import parse_feed
import test_api


class NewsAssetTests(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request

    def page(self, **extra):
        return {'title':'测试文稿','summary':'测试摘要','content':'仅为自动化测试文稿，不是实际新闻。','tags':[],'links':[],'citations':[],**extra}

    def test_manual_and_chat_asset_origins_with_destination(self):
        cid=self.app.store.conversation();self.app.store.message(cid,'assistant','固定测试模型文本')
        mid=self.app.store.messages(cid)[0]['id']
        status,ai=self.request('/api/wiki',{'page':self.page(),'message_id':mid,'category_id':'career'})
        self.assertEqual(status,200)
        status,manual=self.request('/api/wiki',{'page':self.page(title='手写测试文稿'),'category_id':'learning'})
        self.assertEqual(status,200)
        catalog={a['id']:a for a in library.catalog(self.app.store)}
        self.assertEqual((catalog[ai['id']]['origin'],catalog[ai['id']]['category_id']),('ai','career'))
        self.assertEqual(catalog[manual['id']]['origin'],'manual')
        self.request('/api/assets/category',{'id':ai['id'],'category_id':'learning'})
        self.assertEqual(next(a for a in library.catalog(self.app.store) if a['id']==ai['id'])['origin'],'ai')

    def test_invalid_destination_rolls_back_artifact_and_version(self):
        before=len(self.app.store.artifacts());versions=self.app.store.db.execute('SELECT count(*) FROM versions').fetchone()[0]
        self.assertEqual(self.request('/api/wiki',{'page':self.page(),'category_id':'deleted'})[0],409)
        self.assertEqual(len(self.app.store.artifacts()),before)
        self.assertEqual(self.app.store.db.execute('SELECT count(*) FROM versions').fetchone()[0],versions)

    def test_unknown_or_user_message_cannot_claim_ai_origin(self):
        cid=self.app.store.conversation();self.app.store.message(cid,'user','测试用户文本')
        for mid in ['unknown',self.app.store.messages(cid)[0]['id']]:
            self.assertEqual(self.request('/api/wiki',{'page':self.page(),'message_id':mid})[0],400)

    def test_approval_destination_atomic_and_ai_origin(self):
        source=self.app.store.add_source('测试来源','固定测试原文必须逐字引用，不代表真实模型质量。')['source']
        _,job=self.request('/api/jobs',{'kind':'wiki','prompt':'测试整理','source_ids':[source['id']]})
        self.app.store.update_job(job['id'],status='review',proposal={'page':self.page(citations=[{'source_id':source['id'],'quote':source['content']}])})
        before=len(self.app.store.artifacts())
        self.assertEqual(self.request('/api/jobs/'+job['id']+'/approve',{'category_id':'deleted'})[0],409)
        self.assertEqual(self.app.store.job(job['id'])['status'],'review')
        self.assertEqual(len(self.app.store.artifacts()),before)
        status,asset=self.request('/api/jobs/'+job['id']+'/approve',{'category_id':'learning'})
        self.assertEqual(status,200)
        a=next(a for a in library.catalog(self.app.store) if a['id']==asset['id'])
        self.assertEqual((a['origin'],a['category_id']),('ai','learning'))

    def test_feed_future_date_entities_and_plain_text(self):
        rss=b'''<rss><channel><item><title>Local fixture</title><link>https://example.com/a</link><pubDate>Mon, 19 Oct 2026 12:00:00 GMT</pubDate><description>&lt;p&gt;Real text&lt;/p&gt;</description></item><item><title>Future fixture</title><link>https://example.com/b</link><pubDate>Mon, 19 Oct 2099 12:00:00 GMT</pubDate></item></channel></rss>'''
        result=parse_feed(rss,'https://example.com/rss',datetime(2026,10,20,tzinfo=timezone.utc))
        self.assertEqual(len(result),1);self.assertEqual(result[0]['excerpt'],'Real text')
        with self.assertRaises(ValueError):parse_feed(b'<!DOCTYPE rss><rss/>','https://example.com/rss')
        with self.assertRaises(ValueError):parse_feed(b'x'*1500001,'https://example.com/rss')

    def test_collect_real_shape_dedupes_and_does_not_generate(self):
        sub=self.app.weekly.save({'title':'测试订阅','urls':['https://example.com/rss'],'new':True})
        fixture={'title':'Local fixture update','url':'https://example.com/article','published_at':'2026-10-19T00:00:00+00:00','excerpt':'Explicitly labelled fixture source text, not a real public update.','feed_url':'https://example.com/rss'}
        self.assertEqual(self.request('/api/news/refresh',{'id':sub['id']})[0],400)
        with patch('news.fetch_feed',return_value=[fixture]):
            status,first=self.request('/api/news/refresh',{'id':sub['id'],'allow_remote':True})
            source_id=first['items'][0]['source_id']
            library.assign(self.app.store,{'id':source_id,'category_id':'career'})
            status,second=self.request('/api/news/refresh',{'id':sub['id'],'allow_remote':True})
        self.assertEqual(first['added'],1);self.assertEqual(second['added'],0)
        self.assertEqual(len(self.app.news.items()),1);self.assertEqual(self.app.store.jobs(),[])
        self.assertEqual(self.app.store.sources()[0]['url'],fixture['url'])
        self.assertEqual(next(a for a in library.catalog(self.app.store) if a['id']==source_id)['category_id'],'career')

    def test_skill_custom_edit_survives_init(self):
        import task_skills
        original=task_skills.get(self.app.store,'weekly-reading')
        saved=task_skills.save(self.app.store,{**original,'instructions':'用户自己写的规则，必须保留'})
        task_skills.init(self.app.store)
        self.assertEqual(task_skills.get(self.app.store,'weekly-reading')['instructions'],saved['instructions'])

    def test_board_inherits_ai_origin_and_topic_from_linked_document(self):
        page=self.app.store.save_wiki(self.page(diagram=['测试步骤一','测试步骤二']),destination={'category_id':'learning'},origin='ai',reference='fixture_message')
        status,board=self.request('/api/boards/from-wiki',{'id':page['id'],'revision':page['revision']})
        self.assertEqual(status,200)
        item=next(a for a in library.catalog(self.app.store) if a['id']==board['id'])
        self.assertEqual((item['origin'],item['category_id']),('ai','learning'))

    def test_collect_partial_failure_and_no_background_schedule(self):
        sub=self.app.weekly.save({'title':'测试失败订阅','urls':['https://example.com/rss'],'new':True})
        with patch('news.fetch_feed',side_effect=ValueError('明确测试失败')):
            status,result=self.request('/api/news/refresh',{'id':sub['id'],'allow_remote':True})
        self.assertEqual(status,200);self.assertEqual(len(result['warnings']),1)
        self.assertEqual(result['added'],0);self.assertEqual(self.app.store.jobs(),[])
        self.assertTrue(self.app.weekly.manual_only)

    def test_refresh_does_not_silently_skip_fourth_source(self):
        sub=self.app.weekly.save({'title':'测试全部来源','urls':['https://example.com/'+str(i) for i in range(4)],'new':True})
        with patch('news.fetch_feed',return_value=[]) as fetch:
            status,_=self.request('/api/news/refresh',{'id':sub['id'],'allow_remote':True})
        self.assertEqual(status,200);self.assertEqual(fetch.call_count,4)
