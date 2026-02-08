# LLM News

每日自动采集 LLM / AI 领域资讯，经 AI 摘要后生成 **Markdown 日报** + **播报音频（MP3）**，并部署到 GitHub Pages。

## 功能特性

- **多源采集** — arXiv、Hugging Face Papers、Hacker News、GitHub Releases、RSS 博客、Reddit、Twitter/X
- **AI 摘要 & 排序** — 通过 OpenRouter 免费模型自动生成摘要，选出 Top 10 并生成播报文稿
- **语音播报** — Edge TTS（免费）生成 MP3 音频
- **GitHub Pages** — 自动构建并部署每日报告页面
- **Bark 推送** — 可选 iOS 推送通知
- **URL 去重** — 基于 `data/history.json` 避免重复推送
- **GitHub Actions** — 每日定时自动运行，零运维

## 快速开始

### 1. 克隆 & 安装

```bash
git clone https://github.com/<your-username>/llm-news.git
cd llm-news
uv sync
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入你的 API Key
```

| 变量 | 说明 | 必须 |
|------|------|------|
| `OPENROUTER_API_KEY` | [OpenRouter](https://openrouter.ai/keys) API Key | 是 |
| `REDDIT_CLIENT_ID` | [Reddit Apps](https://www.reddit.com/prefs/apps) Client ID | 是 |
| `REDDIT_CLIENT_SECRET` | Reddit Client Secret | 是 |
| `GITHUB_TOKEN` | GitHub Token（提升速率限制） | 否 |
| `BARK_DEVICE_KEY` | [Bark](https://github.com/Finb/Bark) 推送 Key（[获取方式见下方](#bark-推送)） | 否 |

### 3. 运行

```bash
uv run llm-news
# 或指定配置文件
uv run llm-news -c config.yaml
```

输出位于 `output/YYYY-MM-DD/`：

```
output/2026-02-07/
├── daily_report.md          # Markdown 日报
├── daily_report.mp3         # 播报音频
├── broadcast_script.txt     # 播报文稿
└── raw_items.json           # 原始采集数据
```

## 数据来源

| 来源 | 采集方式 | 说明 |
|------|----------|------|
| arXiv | arXiv API | cs.CL / cs.AI / cs.LG，可选按机构过滤 |
| HF Papers | Hugging Face API | 社区精选每日论文 |
| Hacker News | HN API | Top Stories 中 LLM 相关 |
| GitHub | GitHub API | 跟踪仓库 Release Notes |
| 官方博客 | RSS | OpenAI / Google AI / HuggingFace / Microsoft Research |
| Reddit | PRAW | r/MachineLearning, r/LocalLLaMA |
| Twitter/X | Nitter RSS | KOL 推文（默认关闭） |

## 配置

编辑 `config.yaml` 自定义：

- **sources** — 各数据源参数（分类、仓库列表、子版块等）
- **llm** — 模型选择和 OpenRouter 配置
- **tts** — 语音和语速
- **push** — GitHub Pages URL、Bark 推送开关
- **keywords** — LLM 相关关键词过滤列表

## GitHub Actions

项目包含 `.github/workflows/daily.yml`，每日北京时间 08:00 自动运行。

使用方式：
1. Fork 本仓库
2. 在 Settings → Secrets 中添加上述环境变量
3. 启用 GitHub Pages（Source: `gh-pages` 分支）
4. Actions 将自动运行并部署报告

也支持手动触发（`workflow_dispatch`）。

## Bark 推送

[Bark](https://github.com/Finb/Bark) 是一款免费的 iOS 推送工具，可在每日报告生成后向手机发送通知。

1. 在 App Store 下载 [Bark](https://apps.apple.com/app/bark/id1403753865)
2. 打开 App，复制首页显示的 **Device Key**
3. 将 Key 填入 `.env` 的 `BARK_DEVICE_KEY`（或 GitHub Secrets）
4. 确保 `config.yaml` 中 `push.bark_enabled: true`

更多详情参考 [Bark 官方文档](https://github.com/Finb/Bark)。

## 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.12+ |
| 包管理 | uv |
| HTTP | httpx |
| LLM | openai SDK（via OpenRouter 免费模型） |
| TTS | edge-tts |
| 配置 | pydantic-settings + YAML |
| 调度 | GitHub Actions |

## 项目结构

```
llm-news/
├── .github/workflows/daily.yml    # CI/CD
├── src/llm_news/
│   ├── main.py                    # 入口 & 流水线编排
│   ├── config.py                  # 配置加载
│   ├── models.py                  # 数据模型
│   ├── collectors/                # 数据采集器
│   │   ├── arxiv_collector.py
│   │   ├── hf_papers_collector.py
│   │   ├── hackernews_collector.py
│   │   ├── github_collector.py
│   │   ├── blog_collector.py
│   │   ├── reddit_collector.py
│   │   └── twitter_collector.py
│   ├── processor.py               # LLM 摘要 & 排序
│   ├── dedup.py                   # URL 去重
│   ├── tts.py                     # 音频生成
│   ├── output.py                  # 文件输出
│   ├── pages.py                   # GitHub Pages 构建
│   └── push.py                    # Bark 推送
├── config.yaml                    # 配置文件
├── data/                          # 历史记录
├── output/                        # 每日输出
└── pyproject.toml
```

## License

MIT
