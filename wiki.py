"""Local Markdown Wiki projection; SQLite remains the transactional source."""
import json
import os
from pathlib import Path


def sync_wiki(root, store):
    directory=Path(root)/'data/wiki'
    directory.mkdir(parents=True,exist_ok=True)
    pages=[a for a in store.artifacts() if a['kind']=='wiki' and not a['archived']]
    for page in store.artifacts():
        target=directory/(page['id']+'.md')
        if page['kind']=='wiki' and page['archived'] and target.exists():
            archive=directory/'archived';archive.mkdir(exist_ok=True)
            os.replace(target,archive/target.name)
    index=['# 我的知识 Wiki','', '原始资料单独保存；这里只收录确认后的知识页。','']
    for page in pages:
        body=page['body']
        lines=['---','id: '+page['id'],'title: '+json.dumps(page['title'],ensure_ascii=False),'revision: '+str(page['revision']),'tags: '+json.dumps(body['tags'],ensure_ascii=False),'---','','# '+page['title'],'',body['summary'],'',body['content'],'','## 关联页面','']
        lines += ['[['+link+']]' for link in body['links']]
        if body.get('diagram'):
            lines += ['','## 顺序流程图','']
            lines += [str(i+1)+'. '+label for i,label in enumerate(body['diagram'])]
        if body.get('graph'):
            lines += ['','## 画板关系数据','','```json',json.dumps(body['graph'],ensure_ascii=False,indent=2),'```']
        lines += ['','## 原始依据','']
        for cite in body['citations']:
            source=store.source(cite['source_id'])
            lines += ['- '+source['title']+' ('+source['id']+')','> '+cite['quote'],'']
        target=directory/(page['id']+'.md');temporary=target.with_suffix('.tmp')
        temporary.write_text('\n'.join(lines));temporary.chmod(0o600);os.replace(temporary,target)
        index.append('- ['+page['title']+']('+page['id']+'.md)')
    (directory/'index.md').write_text('\n'.join(index))
    return directory
