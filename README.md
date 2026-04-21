# NBA Agent

一个面向中文社区内容的 NBA 日报采集项目。当前版本已经把一条可本地运行的链路串起来：

`采集 -> 关键词过滤 -> 去重 -> 模型二次筛选 -> SQLite 入库 -> 日报输出 / webhook 推送`

它更像一个“可扩展的日报骨架”，重点是把采集、配置、输出和调试流程跑顺，而不是一次性做成完整生产系统。

## 当前能力

- 采集虎扑列表页、球队专区
- 可选采集贴吧社区发现结果
- 拉取 NBA 官方最近两天比赛比分
- 基于关键词做第一轮过滤
- 基于标题 / 链接做去重
- 可选调用兼容 OpenAI 接口的模型做二次筛选
- 自动生成“今日高热度新闻总结”，可选切到模型版
- 写入 SQLite
- 输出到终端、飞书、企业微信
- 支持 `--demo`、`--init-db`、`--hupu-only` 三种常用运行模式

## 暂不包含

- 需要登录态的站点采集
- 完整反爬策略
- 高精度帖子正文解析
- 事件聚类、话题归并、长期画像

## 项目结构

```text
nba-agent/
  nba_agent/
    collectors/   # 采集器
    pipeline/     # 关键词过滤、去重、模型筛选、日报生成
    storage/      # SQLite 存储
    delivery/     # 控制台和 webhook 推送
    scheduler/    # 定时任务入口
  config/         # JSON 配置
  data/           # SQLite 数据库
```

## 运行流程

默认运行时，入口在 [nba_agent/app.py](/Users/yizhou.wu/nba-agent/nba_agent/app.py:1)，整体流程如下：

1. 读取 `config/*.json`
2. 初始化 SQLite
3. 拉取最近两天 NBA 比分
4. 运行虎扑采集器
5. 如果 `config/tieba.json` 中 `enabled=true`，再运行贴吧采集器
6. 执行关键词过滤
7. 执行去重
8. 如果模型配置完整且 `enabled=true`，执行模型二次筛选
9. 生成“今日高热度新闻总结”；如果 `summary_enabled=true` 且模型配置完整，则优先使用模型版，否则回退到规则版总结
10. 入库并生成日报
11. 输出到终端，并按配置推送到飞书 / 企业微信

## 快速开始

### 1. 安装依赖

```bash
cd /Users/yizhou.wu/nba-agent
pip3 install -e .
```

安装后可以直接使用命令行入口：

```bash
nba-agent --help
```

如果你不想安装，也可以继续用模块方式运行：

```bash
python3 -m nba_agent.app --help
```

### 2. 初始化数据库

```bash
python3 -m nba_agent.app --init-db
```

数据库默认写到 [data/nba_agent.db](/Users/yizhou.wu/nba-agent/data/nba_agent.db)。

### 3. 先跑一遍 demo

```bash
python3 -m nba_agent.app --demo
```

`--demo` 不依赖真实站点，适合先验证整条链路：

- 配置读取是否正常
- 关键词过滤是否命中
- 去重是否生效
- 日报输出格式是否符合预期

### 4. 跑真实采集

```bash
python3 -m nba_agent.app
```

如果只想看虎扑采集：

```bash
python3 -m nba_agent.app --hupu-only
```

## 命令行参数

当前入口只支持 3 个参数：

- `--demo`：使用内置模拟数据跑整条流水线
- `--init-db`：初始化 SQLite 表结构后退出
- `--hupu-only`：只运行虎扑采集器，不跑贴吧采集

## 配置总览

项目主要配置都在 `config/` 目录下：

| 文件 | 作用 |
| --- | --- |
| [config/keywords.json](/Users/yizhou.wu/nba-agent/config/keywords.json:1) | 关键词、分类、组合规则 |
| [config/hupu.json](/Users/yizhou.wu/nba-agent/config/hupu.json:1) | 虎扑入口和球队专区 |
| [config/tieba.json](/Users/yizhou.wu/nba-agent/config/tieba.json:1) | 贴吧社区发现和实验抓帖开关 |
| [config/agent_filter.json](/Users/yizhou.wu/nba-agent/config/agent_filter.json:1) | 模型二次筛选与热度总结 |
| [config/report.json](/Users/yizhou.wu/nba-agent/config/report.json:1) | 日报条数和来源限流 |
| [config/delivery.json](/Users/yizhou.wu/nba-agent/config/delivery.json:1) | 终端 / 飞书 / 企业微信推送 |

## 最常改的 4 个配置

### 关键词规则

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
    ["湖人", "交易"]
  ]
}
```

关键字段：

- `terms`：结构化关键词，支持别名、弱别名和误命中排除
- `category`：关键词分类，常见值是 `player` / `team` / `topic`
- `exclude_any`：命中任一排除词就丢弃
- `groups`：写规范化后的关键词组合，命中后会提升条目权重

### 虎扑配置

当前代码默认一定会跑虎扑采集器，配置在 [config/hupu.json](/Users/yizhou.wu/nba-agent/config/hupu.json:1)。

当前仓库里的实际配置重点是：

- `max_detail_fetches=10`
- 已启用 `hupu_mobile_home`
- 已启用 `hupu_basketball_news`
- 已启用 `hupu_nba_board`
- 已启用 `lakers`、`warriors` 两个球队专区

字段说明：

- `list_sources[].enabled`：控制某个入口是否启用
- `list_sources[].max_items`：该入口最多抓多少条列表结果
- `max_detail_fetches`：本次任务最多抓多少个详情页正文
- `zone_template`：球队专区 URL 模板
- `team_presets[].enabled`：是否启用某个球队专区

### 贴吧配置

配置文件是 [config/tieba.json](/Users/yizhou.wu/nba-agent/config/tieba.json:1)。

当前仓库里的实际默认值是：

```json
{
  "enabled": false,
  "max_forums_per_query": 3,
  "query_categories": ["team", "player"],
  "experimental_thread_fetch_enabled": false,
  "experimental_thread_fetch_mode": "ws",
  "max_forums_for_threads": 4,
  "max_threads_per_forum": 10
}
```

说明：

- `enabled`：是否启用贴吧采集器；当前默认关闭
- `max_forums_per_query`：每个关键词最多保留多少个贴吧社区候选
- `query_categories`：哪些关键词分类参与贴吧社区发现
- `experimental_thread_fetch_enabled`：是否启用实验性贴吧帖子抓取
- `experimental_thread_fetch_mode`：当前只支持 `ws`

注意：

- 当前稳定路径是“贴吧社区发现”，适合补充话题入口
- 实验性帖子抓取依赖 `aiotieba`，默认关闭更稳妥

### 模型二次筛选

配置文件是 [config/agent_filter.json](/Users/yizhou.wu/nba-agent/config/agent_filter.json:1)。

当前仓库配置：

```json
{
  "enabled": false,
  "summary_enabled": true,
  "api_base_url": "${NBA_AGENT_OPENAI_BASE}",
  "api_key": "${NBA_AGENT_OPENAI_API_KEY}",
  "model": "${NBA_AGENT_OPENAI_MODEL}",
  "api_mode": "responses",
  "reasoning_effort": "medium",
  "timeout_seconds": 12,
  "batch_size": 8,
  "min_score": 6,
  "summary_top_n": 5
}
```

这部分和代码行为有两个关键点：

- 只有当 `api_base_url`、`api_key`、`model` 都成功从环境变量展开出来时，模型筛选和“模型版总结”才会真正启用
- 当前代码不会彻底关闭总结区块；未启用模型版总结时，会自动回退到规则版总结

字段说明：

- `enabled`：是否开启模型二次筛选
- `summary_enabled`：是否优先使用模型生成“今日高热度新闻总结”
- `api_mode`：支持 `chat_completions` 和 `responses`
- `reasoning_effort`：主要用于 `responses` 模式
- `batch_size`：每批喂给模型多少条候选
- `min_score`：模型评分低于这个阈值就丢弃
- `summary_top_n`：用于生成热点总结的候选条数

推荐环境变量：

```bash
export NBA_AGENT_OPENAI_BASE='https://api.openai.com/v1'
export NBA_AGENT_OPENAI_API_KEY='sk-xxx'
export NBA_AGENT_OPENAI_MODEL='gpt-5.4-mini'
```

## 其他配置

### 日报输出长度

配置文件是 [config/report.json](/Users/yizhou.wu/nba-agent/config/report.json:1)。

当前仓库值：

```json
{
  "overview_top_n": 10,
  "category_top_n": 10,
  "per_source_top_n": 0
}
```

说明：

- `overview_top_n`：总览区最多保留多少条
- `category_top_n`：每个分类区最多保留多少条
- `per_source_top_n`：每个区段单一来源最多保留多少条；`0` 在加载后等价于“不限制”

### 推送配置

配置文件是 [config/delivery.json](/Users/yizhou.wu/nba-agent/config/delivery.json:1)。

代码支持：

- `console.enabled`
- `feishu.enabled / webhook_url / secret / msg_type`
- `wecom.enabled / webhook_url / secret / msg_type`

推荐把仓库内配置写成环境变量占位符，例如：

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

最小示例：

```bash
export FEISHU_BOT_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/xxx'
python3 -m nba_agent.app
```

或：

```bash
export WECOM_BOT_WEBHOOK='https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx'
python3 -m nba_agent.app
```

## 日报里会看到什么

当前日报生成逻辑在 [nba_agent/pipeline/report.py](/Users/yizhou.wu/nba-agent/nba_agent/pipeline/report.py:1)，输出通常包含这些区块：

- 最近两天比赛比分
- 今日高热度新闻总结
- 总结输入 Top
- 运行耗时
- 来源概览
- 总览
- 按分类拆分的球队 / 球员 / 主题区块
- 运行诊断

单条内容里可能包含：

- 命中关键词
- 命中分类
- Agent评分
- Agent理由
- 摘要
- 原文链接

## 常见运行方式

### 只验证本地逻辑

```bash
python3 -m nba_agent.app --demo
```

### 初始化数据库但不采集

```bash
python3 -m nba_agent.app --init-db
```

### 只观察虎扑抓取效果

```bash
python3 -m nba_agent.app --hupu-only
```

### 安装成命令后运行

```bash
nba-agent
nba-agent --demo
nba-agent --hupu-only
```

## 常见问题

### 1. 为什么模型没有生效

先看运行诊断。当前代码只有在下面三个值都非空时才会启用模型：

- `NBA_AGENT_OPENAI_BASE`
- `NBA_AGENT_OPENAI_API_KEY`
- `NBA_AGENT_OPENAI_MODEL`

如果你刚改完 shell 配置，先执行：

```bash
source ~/.zshrc
```

### 2. 为什么 collected=0

优先检查：

- 当前网络是否能访问虎扑、贴吧和 NBA 官方源
- `config/hupu.json` 里是否把入口都关掉了
- `config/tieba.json` 里是否关闭了贴吧且关键词又过严

### 3. 为什么贴吧没有输出

当前仓库默认 `config/tieba.json` 里 `enabled=false`。这不是 bug，是默认配置就是关闭的。

### 4. 为什么没有模型筛选，但还是有总结

这是当前代码允许的行为。如果：

- `enabled=false`
- 或者模型环境变量不完整

那么系统会跳过“二次筛选”。但当前代码仍会生成“今日高热度新闻总结”，只是这时通常是规则版总结，而不是模型版总结。

## 安全建议

- 仓库里的 `config/*.json` 尽量只保留 `${ENV_VAR}` 占位符
- 不要提交真实 `webhook_url`、`secret`、`api_key`
- 提交前至少执行一次：

```bash
rg -n "hook/|sk-|AKIA|AIza|api_key|secret" config README.md nba_agent
```

## 定时任务

定时任务入口在 [daily_job.py](/Users/yizhou.wu/nba-agent/nba_agent/scheduler/daily_job.py:1)：

```python
from nba_agent.app import run_pipeline


def daily_job() -> None:
    run_pipeline(demo=False)
```

它只是复用主流程，没有额外的调度逻辑。接 crontab、launchd 或其他任务系统时，直接调用这个入口即可。

## 下一步更值得做什么

1. 增强虎扑和贴吧正文解析质量，降低标题党和噪声
2. 把贴吧从“社区发现”推进到更稳定的帖子级采集
3. 增加赛程、伤病、交易等事实型结构化来源
4. 给飞书和企业微信补结构化卡片模板
5. 在热点总结之前增加事件聚类，避免多条内容讲同一件事
