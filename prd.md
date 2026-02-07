# LLM News - 每日大模型资讯聚合与播报

## 1. 项目概述

每天自动采集 LLM 领域资讯，经 AI 摘要后生成：
- **每日播报音频**（英文，5-10 分钟，Top 10 资讯 + 简要点评）
- **Markdown 日报**（含摘要 + 原文链接）

所有产物输出到本地 `output/` 目录，后续可扩展邮件/Webhook 等推送渠道。

关注领域：OpenAI, Claude/Anthropic, Google/Gemini, DeepSeek, Qwen, Kimi/Moonshot, LLaMA/Meta, vLLM, SGLang 及所有 LLM 相关技术。

---

## 2. 信息采集模块

| 来源 | 采集方式 | 说明 |
|------|----------|------|
| **arXiv** | arXiv API | 分类：cs.CL, cs.AI, cs.LG；按关键词过滤 LLM 相关论文 |
| **官方博客** | RSS / 网页抓取 | OpenAI Blog, Anthropic Blog, Google AI Blog, DeepSeek Blog, Qwen Blog 等 |
| **GitHub** | GitHub API | 跟踪关键仓库的 Release Notes + Trending（LLM 相关） |
| **Twitter/X** | 抓取固定 KOL 列表 | 预设关注的 LLM 领域意见领袖推文 |
| **Reddit** | Reddit API (PRAW) | r/MachineLearning, r/LocalLLaMA 等子版块热帖 |

### 关键词过滤列表（可配置）
```
LLM, large language model, GPT, Claude, Gemini, DeepSeek, Qwen,
transformer, RLHF, DPO, inference, quantization, fine-tuning,
RAG, agent, reasoning, multimodal, tokenizer, vLLM, SGLang,
LLaMA, Mistral, GGUF, LoRA, MoE, ...
```

---

## 3. 内容加工模块

### 3.1 LLM 摘要 & 文稿生成
- **接口**：OpenRouter（OpenAI 兼容接口），统一 base_url + api_key
- **免费模型**（OpenRouter `:free` 后缀 = $0）：
  - `google/gemma-3-27b-it:free`（默认）
  - `meta-llama/llama-3.3-70b-instruct:free`
  - `qwen/qwen-2.5-72b-instruct:free`
  - `deepseek/deepseek-r1:free`
  - 完整列表：https://openrouter.ai/models?q=free
- **流程**：
  1. 对每条资讯生成简短摘要（1-2 句）
  2. 按重要性/热度排序，选出 Top 10
  3. 生成播报文稿（英文，含开场白 + 逐条播报 + 结尾）
  4. 生成 Markdown 日报

### 3.2 去重
- 基于 URL 去重，使用 JSON 文件记录已推送内容
- 文件路径：`data/history.json`

---

## 4. 音频生成模块

- **引擎**：Edge TTS（微软免费 TTS，无需 API Key）
- **语言**：英文
- **语音**：可配置（默认 en-US-AriaNeural，自然度高）
- **时长**：5-10 分钟
- **输出格式**：MP3
- **成本**：$0（完全免费，无速率限制问题）

---

## 5. 本地输出模块

所有产物输出到 `output/YYYY-MM-DD/` 目录：

```
output/2026-02-07/
├── daily_report.md        # Markdown 日报（Top 10 摘要 + 链接）
├── daily_report.mp3       # 播报音频
└── raw_items.json         # 原始采集数据（备查）
```

- **Markdown 日报**：含日期标题 + Top 10 资讯卡片（标题、摘要、来源标签、原文链接）
- **MP3 音频**：基于播报文稿生成
- **原始数据**：JSON 格式保存当日全部采集条目，方便调试和回溯

> 推送模块（邮件/Webhook 等）后续扩展，当前阶段仅本地输出。

---

## 6. 运行方式

- **调度**：GitHub Actions 定时触发（每日 UTC 固定时间）
- **存储**：JSON 文件存储历史记录（提交回仓库 or Artifact）

---

## 7. 技术栈

| 组件 | 技术选型 |
|------|----------|
| 语言 | Python 3.12+ |
| 包管理 | uv |
| HTTP 请求 | httpx |
| arXiv | arxiv (PyPI) |
| Reddit | praw |
| RSS 解析 | feedparser |
| LLM 调用 | openai（通过 OpenRouter 免费模型） |
| TTS | edge-tts（免费） |
| 输出 | 本地文件（Markdown + MP3 + JSON） |
| 数据存储 | JSON 文件 |
| 调度 | GitHub Actions (cron) |
| 配置管理 | pydantic-settings (.env) |

---

## 8. 配置文件结构

```yaml
# config.yaml
sources:
  arxiv:
    categories: ["cs.CL", "cs.AI", "cs.LG"]
    max_results: 50
  blogs:
    - name: "OpenAI"
      url: "https://openai.com/blog/rss"
    - name: "Anthropic"
      url: "https://www.anthropic.com/rss"
    # ...
  github:
    repos:
      - "vllm-project/vllm"
      - "sgl-project/sglang"
      - "meta-llama/llama"
      # ...
    trending_topic: "LLM"
  twitter:
    kol_list:
      - "@kaboroevich"
      - "@_akhaliq"
      - "@swaboroevich"
      # ...
  reddit:
    subreddits: ["MachineLearning", "LocalLLaMA"]
    time_filter: "day"
    limit: 25

llm:
  provider: "gemini"           # gemini (免费) | openai | groq
  # Gemini 免费层配置 (默认)
  gemini_api_key: "${GEMINI_API_KEY}"
  gemini_model: "gemini-2.0-flash"
  # OpenAI 兼容接口配置 (备选)
  base_url: "https://api.openai.com/v1"
  api_key: "${OPENAI_API_KEY}"
  model: "gpt-4o-mini"

tts:
  voice: "en-US-AriaNeural"
  rate: "+10%"

output:
  dir: "output"               # 本地输出目录

keywords:
  - "LLM"
  - "large language model"
  - "GPT"
  - "Claude"
  # ...
```

---

## 9. 项目结构

```
llm-news/
├── .github/
│   └── workflows/
│       └── daily.yml          # GitHub Actions workflow
├── src/
│   └── llm_news/
│       ├── __init__.py
│       ├── main.py            # 入口
│       ├── config.py          # 配置加载 (pydantic-settings)
│       ├── collectors/        # 信息采集
│       │   ├── __init__.py
│       │   ├── arxiv.py
│       │   ├── blog.py
│       │   ├── github.py
│       │   ├── twitter.py
│       │   └── reddit.py
│       ├── processor.py       # LLM 摘要 & 排序 & 文稿生成
│       ├── tts.py             # Edge TTS 音频生成
│       ├── output.py          # 本地输出（Markdown + JSON）
│       ├── dedup.py           # 去重逻辑
│       └── models.py          # 数据模型 (dataclass / pydantic)
├── data/
│   └── history.json           # 已推送记录
├── output/                    # 每日输出目录
│   └── 2026-02-07/
│       ├── daily_report.md
│       ├── daily_report.mp3
│       └── raw_items.json
├── config.yaml                # 配置文件
├── pyproject.toml
└── README.md
```

---

## 10. 核心流程

```
[定时触发 GitHub Actions]
        │
        ▼
  ┌─────────────┐
  │  加载配置     │
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  并行采集     │ ← arXiv / Blog / GitHub / Twitter / Reddit
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  去重过滤     │ ← 基于 history.json 的 URL 去重
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  LLM 摘要    │ ← OpenAI 兼容接口
  │  排序 Top10  │
  │  生成文稿     │
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  Edge TTS    │ → 生成 MP3 音频
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  本地输出     │ → output/YYYY-MM-DD/ (MD + MP3 + JSON)
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  更新历史     │ → 写入 history.json
  └─────────────┘
```

---

## 11. 环境变量 (Secrets)

| 变量名 | 说明 | 是否必须 |
|--------|------|----------|
| `OPENROUTER_API_KEY` | OpenRouter API Key | 是 |
| `REDDIT_CLIENT_ID` | Reddit API Client ID（免费） | 是 |
| `REDDIT_CLIENT_SECRET` | Reddit API Client Secret（免费） | 是 |
| `GITHUB_TOKEN` | GitHub API Token（Actions 自带） | 否 |

### 免费服务清单

| 服务 | 免费额度 | 获取方式 |
|------|----------|----------|
| **OpenRouter** | `:free` 模型无限免费 | [openrouter.ai/keys](https://openrouter.ai/keys) 注册 |
| **Edge TTS** | 无限制 | 无需注册，直接调用 |
| **Reddit API** | 100 QPM (免费) | [Reddit Apps](https://www.reddit.com/prefs/apps) 注册 |
| **GitHub API** | 5000 req/h (with token) | Actions 自带 GITHUB_TOKEN |
| **arXiv API** | 无限制（建议 3s 间隔） | 无需注册 |