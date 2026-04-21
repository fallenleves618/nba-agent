# NBA Agent

一个面向中文社区内容的 NBA 日报采集骨架，目标是把“采集 -> 关键词过滤 -> 去重 -> 入库 -> 日报输出”先跑通。

当前版本重点是项目结构和本地可运行流程：

- 支持关键词配置
- 支持 SQLite 存储
- 支持控制台日报输出
- 支持展示 NBA 官方最近两天比赛比分
- 支持可选的模型二次筛选
- 支持 `--demo` 模式验证流水线
- 已预留虎扑、贴吧、官方信息源 collector 骨架

当前不包含：

- 真实站点登录
- 复杂反爬
- 完整 HTML 解析规则
- LLM 摘要与聚类

## 目录

```text
nba_agent/
  collectors/    # 站点采集器
  pipeline/      # 过滤、去重、日报生成
  storage/       # SQLite 持久化
  delivery/      # 输出渠道
  scheduler/     # 定时任务入口
  config/        # 关键词配置
```

## 快速开始

```bash
cd /Users/yizhou.wu/nba-agent
python3 -m nba_agent.app --demo
```

初始化数据库：

```bash
python3 -m nba_agent.app --init-db
```

运行真实 collector 骨架：

```bash
python3 -m nba_agent.app
```

说明：

- `--demo` 会生成几条模拟内容，验证关键词过滤、去重、入库、日报流程。
- 不加 `--demo` 时会执行当前 collector。虎扑入口和球队专区已经改成配置驱动；贴吧默认走稳定的社区发现模式，另外预留了默认关闭的实验性帖子抓取开关。
- 日报顶部会展示 NBA 官方最近两天有实际比分的比赛日，数据来自 `scheduleLeagueV2.json`。
- 如果开启 `config/agent_filter.json`，会在关键词筛选和去重之后，再调用模型做一次保留/丢弃判断。
- 日报输出条数也支持配置，见 `config/report.json`。
- 日报现在支持 `console + 飞书 + 企业微信` 推送，见 `config/delivery.json`。
- 日报会额外展示 `运行耗时`、`总结输入 Top`，并在条目里显示 `Agent评分 / Agent理由`。

## 配置关键词

编辑 [config/keywords.json](/Users/yizhou.wu/nba-agent/config/keywords.json:1)：

```json
{
  "include_any": [],
  "terms": [
    {
      "name": "勒布朗-詹姆斯",
      "category": "player",
      "aliases": ["勒布朗-詹姆斯", "勒布朗", "老詹", "lbj"],
      "weak_aliases": ["詹姆斯"],
      "exclude_aliases": ["詹姆斯-哈登", "james harden"]
    },
    {
      "name": "斯蒂芬-库里",
      "category": "player",
      "aliases": ["斯蒂芬-库里", "斯蒂芬", "steph curry"],
      "weak_aliases": ["库里"],
      "exclude_aliases": ["塞思-库里", "seth curry", "小库里"]
    },
    {
      "name": "湖人",
      "category": "team",
      "aliases": ["湖人", "lakers"]
    },
    {
      "name": "交易",
      "category": "topic",
      "aliases": ["交易", "转会", "签约"]
    }
  ],
  "exclude_any": ["CBA", "英超", "足球", "电竞"],
  "groups": [
    ["勒布朗-詹姆斯", "伤病"],
    ["斯蒂芬-库里", "复出"],
    ["湖人", "交易"]
  ]
}
```

单独验证虎扑 collector：

```bash
python3 -m nba_agent.app --hupu-only
```

过滤规则：

- `terms`：结构化关键词，支持别名、弱别名和误命中排除
- `category`：给关键词打分类，例如 `player` / `team` / `topic`
- `include_any`：兼容旧格式，不建议和 `terms` 混用
- `exclude_any`：命中任一排除词即丢弃
- `groups`：写规范化后的关键词名，如果命中组合，会给更高优先级

## 配置虎扑入口

编辑 [config/hupu.json](/Users/yizhou.wu/nba-agent/config/hupu.json:1)：

```json
{
  "max_detail_fetches": 12,
  "zone_template": {
    "name_template": "hupu_team_zone_{key}",
    "url_template": "https://bbs.hupu.com/{slug}"
  },
  "list_sources": [
    {
      "name": "hupu_mobile_home",
      "url": "https://m.hupu.com/home",
      "enabled": true,
      "max_items": 20
    },
    {
      "name": "hupu_basketball_news",
      "url": "https://bbs.hupu.com/502",
      "enabled": true,
      "max_items": 20
    }
  ],
  "team_presets": [
    {
      "key": "lakers",
      "label": "湖人专区",
      "slug": "lakers",
      "enabled": true,
      "max_items": 20
    },
    {
      "key": "warriors",
      "label": "勇士专区",
      "slug": "warriors",
      "enabled": true,
      "max_items": 20
    }
  ]
}
```

说明：

- `enabled`：控制是否启用这个入口
- `max_items`：该入口最多取多少条列表结果
- `max_detail_fetches`：本次任务最多抓多少个详情页正文
- `zone_template`：专区 URL 模板，`team_presets` 会按它自动展开成真实入口
- `team_presets`：内置了整套常用 NBA 球队专区预设，只需要开关 `enabled` 或调整 `slug`

## 配置贴吧入口

编辑 [config/tieba.json](/Users/yizhou.wu/nba-agent/config/tieba.json:1)：

```json
{
  "max_forums_per_query": 3,
  "query_categories": ["team", "player"],
  "experimental_thread_fetch_enabled": false,
  "experimental_thread_fetch_mode": "ws",
  "max_forums_for_threads": 4,
  "max_threads_per_forum": 10
}
```

说明：

- `max_forums_per_query`：每个关键词最多保留多少个贴吧社区候选
- `query_categories`：哪些关键词分类参与贴吧社区发现，默认只用 `team / player`
- `experimental_thread_fetch_enabled`：是否启用实验性贴吧帖子抓取，默认关闭
- `experimental_thread_fetch_mode`：当前只支持 `ws`
- `max_forums_for_threads`：实验抓取最多尝试多少个贴吧
- `max_threads_per_forum`：每个贴吧最多抓多少条帖子

注意：

- 当前默认模式是稳定的“贴吧社区发现”，会产出真实贴吧 URL、简介、成员数和主题数
- 实验性帖子抓取依赖 `aiotieba`，默认不开，因为当前贴吧线程流在部分吧会出现内容漂移，只建议显式试验，不建议默认信任

## 配置日报长度

编辑 [config/report.json](/Users/yizhou.wu/nba-agent/config/report.json:1)：

```json
{
  "overview_top_n": 10,
  "category_top_n": 8,
  "per_source_top_n": 0
}
```

说明：

- `overview_top_n`：总览区最多保留多少条
- `category_top_n`：每个分类分组最多保留多少条
- `per_source_top_n`：每个区段里单一来源最多保留多少条，`0` 表示不限制

## 配置模型筛选

编辑 [config/agent_filter.json](/Users/yizhou.wu/nba-agent/config/agent_filter.json:1)：

```json
{
  "enabled": false,
  "summary_enabled": false,
  "api_base_url": "${NBA_AGENT_OPENAI_BASE}",
  "api_key": "${NBA_AGENT_OPENAI_API_KEY}",
  "model": "${NBA_AGENT_OPENAI_MODEL}",
  "api_mode": "chat_completions",
  "reasoning_effort": "${NBA_AGENT_OPENAI_REASONING_EFFORT}",
  "timeout_seconds": 20,
  "batch_size": 8,
  "min_score": 6,
  "summary_top_n": 8
}
```

说明：

- `enabled`：是否开启模型二次筛选，默认关闭
- `summary_enabled`：是否开启“今日高热度新闻总结”，默认关闭
- `api_base_url`：兼容 OpenAI Chat Completions 的基础地址，例如 `https://api.openai.com/v1`
- `api_key`：模型服务的 API Key，建议通过环境变量注入
- `model`：模型名
- `api_mode`：接口风格，支持 `chat_completions` 和 `responses`
- `reasoning_effort`：推理强度，主要用于 `responses` 模式
- `batch_size`：每次打给模型多少条候选，控制成本和上下文长度
- `min_score`：模型评分达到多少才保留到最终日报
- `summary_top_n`：生成热度总结时，最多喂给模型多少条候选

开启后，流程会变成：

1. collector 抓取候选内容
2. 关键词规则做第一轮过滤
3. 去重
4. 模型判断 `keep / score / reason`
5. 只保留模型认可的内容进入存储和日报

如果同时开启 `summary_enabled`，日报顶部还会新增“今日高热度新闻总结”区块。

## 配置推送

编辑 [config/delivery.json](/Users/yizhou.wu/nba-agent/config/delivery.json:1)：

```json
{
  "console": {
    "enabled": true
  },
  "feishu": {
    "enabled": false,
    "webhook_url": "${FEISHU_BOT_WEBHOOK}",
    "secret": "${FEISHU_BOT_SECRET}",
    "msg_type": "text"
  },
  "wecom": {
    "enabled": false,
    "webhook_url": "${WECOM_BOT_WEBHOOK}",
    "secret": "",
    "msg_type": "markdown"
  }
}
```

说明：

- `console.enabled`：是否继续输出到终端
- `feishu.enabled` / `wecom.enabled`：是否启用该推送渠道
- `webhook_url`：支持直接写值，也支持 `${ENV_VAR}` 形式读取环境变量
- `feishu.secret`：飞书机器人如果启用了签名校验，就把密钥放这里；没启用可留空
- `msg_type`：飞书支持 `text` / `post`，企业微信支持 `text` / `markdown`

最小用法：

```bash
export FEISHU_BOT_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/xxx'
python3 -m nba_agent.app
```

或：

```bash
export WECOM_BOT_WEBHOOK='https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx'
python3 -m nba_agent.app
```

定时任务 [daily_job.py](/Users/yizhou.wu/nba-agent/nba_agent/scheduler/daily_job.py:1) 不需要额外改动，配置好后会直接沿用推送设置。

## 下一步建议

1. 继续验证贴吧帖子级源，找到能稳定替换实验 `ws` 路径的正式接口
2. 增加事实源，例如 NBA 官方赛程 / 比分 API
3. 在去重后增加事件聚类和 LLM 摘要
4. 增加结构化推送模板，例如飞书卡片和企业微信重点摘要版
