"""Public source presets. Choosing a site does not enable periodic collection."""
SITES = [
    {'id':'openai','name':'OpenAI','url':'https://openai.com/news/','feed_url':'https://openai.com/news/rss.xml','note':'官方新闻；周刊使用RSS订阅源'},
    {'id':'anthropic','name':'Claude / Anthropic','url':'https://www.anthropic.com/news','note':'按 Cloud 指 Claude 理解；当前网络被安全策略拦截，可取消或修改'},
    {'id':'deepseek','name':'DeepSeek','url':'https://api-docs.deepseek.com/'},
    {'id':'doubao','name':'豆包','url':'https://docs.volcengine.com/docs/82379','note':'豆包模型官方文档，不等于豆包工作公告'},
    {'id':'36kr','name':'36氪','url':'https://36kr.com/','note':'动态网站，正文可读性需每次校验'}
]
