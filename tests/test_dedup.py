"""Tests for multi-layer deduplication logic.

测试多层去重策略：URL 标准化 / 规范 ID / 标题匹配 / 来源优先级。
"""

from datetime import datetime, timezone

import pytest

from llm_news.dedup import (
    SOURCE_PRIORITY,
    deduplicate,
    extract_canonical_key,
    normalize_title,
    normalize_url,
)
from llm_news.models import NewsItem


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_item(
    title: str = "Test Item",
    url: str = "https://example.com/test",
    source: str = "blog",
    source_name: str = "Test",
    content: str = "",
) -> NewsItem:
    return NewsItem(
        title=title,
        url=url,
        source=source,
        source_name=source_name,
        content=content,
    )


def _empty_history() -> dict[str, set[str]]:
    return {"urls": set(), "canonical_keys": set()}


# ── normalize_url tests ──────────────────────────────────────────────────


class TestNormalizeUrl:
    """URL 标准化测试"""

    def test_trailing_slash(self):
        """去尾斜杠"""
        assert normalize_url("https://openai.com/index/testing-ads-in-chatgpt/") == \
               normalize_url("https://openai.com/index/testing-ads-in-chatgpt")

    def test_http_to_https(self):
        """http → https"""
        assert normalize_url("http://arxiv.org/abs/2602.06570v1") == \
               normalize_url("https://arxiv.org/abs/2602.06570v1")

    def test_remove_www(self):
        """去 www"""
        assert normalize_url("https://www.example.com/page") == \
               normalize_url("https://example.com/page")

    def test_strip_tracking_params(self):
        """去追踪参数"""
        assert normalize_url("https://example.com/page?utm_source=twitter&id=123") == \
               "https://example.com/page?id=123"

    def test_empty_url(self):
        """空 URL"""
        assert normalize_url("") == ""

    def test_case_insensitive_host(self):
        """域名大小写不敏感"""
        assert normalize_url("https://EXAMPLE.COM/Page") == "https://example.com/Page"

    def test_strip_fragment(self):
        """去 fragment"""
        assert normalize_url("https://example.com/page#section") == \
               "https://example.com/page"


# ── extract_canonical_key tests ──────────────────────────────────────────


class TestExtractCanonicalKey:
    """跨源规范 ID 提取测试"""

    def test_arxiv_abs_url(self):
        """arxiv.org/abs/ URL"""
        item = _make_item(url="http://arxiv.org/abs/2602.06570v1", source="arxiv")
        assert extract_canonical_key(item) == "arxiv:2602.06570"

    def test_arxiv_pdf_url(self):
        """arxiv.org/pdf/ URL"""
        item = _make_item(url="https://arxiv.org/pdf/2602.06570v1.pdf", source="arxiv")
        assert extract_canonical_key(item) == "arxiv:2602.06570"

    def test_hf_papers_url(self):
        """huggingface.co/papers/ URL"""
        item = _make_item(url="https://huggingface.co/papers/2602.06570", source="hf_papers")
        assert extract_canonical_key(item) == "arxiv:2602.06570"

    def test_arxiv_and_hf_same_key(self):
        """arxiv 和 hf_papers 同一论文产生相同 canonical key"""
        arxiv_item = _make_item(url="http://arxiv.org/abs/2602.06570v1", source="arxiv")
        hf_item = _make_item(url="https://huggingface.co/papers/2602.06570", source="hf_papers")
        assert extract_canonical_key(arxiv_item) == extract_canonical_key(hf_item)

    def test_non_arxiv_url(self):
        """非 arxiv URL 返回 None"""
        item = _make_item(url="https://openai.com/blog/test", source="blog")
        assert extract_canonical_key(item) is None

    def test_github_url(self):
        """GitHub URL 返回 None"""
        item = _make_item(url="https://github.com/openai/gpt", source="github")
        assert extract_canonical_key(item) is None


# ── normalize_title tests ────────────────────────────────────────────────


class TestNormalizeTitle:
    """标题标准化测试"""

    def test_case_insensitive(self):
        """大小写不敏感"""
        assert normalize_title("Testing Ads in ChatGPT") == \
               normalize_title("Testing ads in ChatGPT")

    def test_strip_punctuation(self):
        """去标点"""
        assert normalize_title("Hello, World!") == "hello world"

    def test_collapse_whitespace(self):
        """合并空格"""
        assert normalize_title("Hello   World") == "hello world"

    def test_colon_in_title(self):
        """标题中的冒号"""
        t1 = normalize_title("Baichuan-M3: Modeling Clinical Inquiry for Reliable Medical Decision-Making")
        t2 = normalize_title("Baichuan-M3: Modeling Clinical Inquiry for Reliable Medical Decision-Making")
        assert t1 == t2


# ── deduplicate integration tests ────────────────────────────────────────


class TestDeduplicateIntegration:
    """去重集成测试"""

    def test_case1_arxiv_vs_hf_papers(self):
        """Case 1: 同一论文出现在 arxiv 和 hf_papers（用户实际场景）

        Baichuan-M3 同时出现在 hf_papers 和 arxiv，应去重为 1 条，
        保留 arxiv（原始来源，优先级更高）。
        """
        hf_item = _make_item(
            title="Baichuan-M3: Modeling Clinical Inquiry for Reliable Medical Decision-Making",
            url="https://huggingface.co/papers/2602.06570",
            source="hf_papers",
            source_name="HF Daily Papers",
        )
        arxiv_item = _make_item(
            title="Baichuan-M3: Modeling Clinical Inquiry for Reliable Medical Decision-Making",
            url="http://arxiv.org/abs/2602.06570v1",
            source="arxiv",
            source_name="CL",
        )
        result = deduplicate([hf_item, arxiv_item], _empty_history())
        assert len(result) == 1
        assert result[0].source == "arxiv"  # 原始来源优先

    def test_case1_arxiv_first(self):
        """arxiv 先出现时也应保留 arxiv"""
        arxiv_item = _make_item(
            title="Baichuan-M3: Modeling Clinical Inquiry for Reliable Medical Decision-Making",
            url="http://arxiv.org/abs/2602.06570v1",
            source="arxiv",
            source_name="CL",
        )
        hf_item = _make_item(
            title="Baichuan-M3: Modeling Clinical Inquiry for Reliable Medical Decision-Making",
            url="https://huggingface.co/papers/2602.06570",
            source="hf_papers",
            source_name="HF Daily Papers",
        )
        result = deduplicate([arxiv_item, hf_item], _empty_history())
        assert len(result) == 1
        assert result[0].source == "arxiv"

    def test_case2_blog_vs_hackernews(self):
        """Case 2: 同一博文出现在 blog 和 hackernews（URL 尾斜杠差异）

        OpenAI ChatGPT 广告测试文章同时出现在 blog 和 hackernews，
        URL 仅差末尾 /，应去重为 1 条，保留 blog（原始来源）。
        """
        hn_item = _make_item(
            title="Testing Ads in ChatGPT",
            url="https://openai.com/index/testing-ads-in-chatgpt/",
            source="hackernews",
            source_name="Hacker News",
        )
        blog_item = _make_item(
            title="Testing ads in ChatGPT",
            url="https://openai.com/index/testing-ads-in-chatgpt",
            source="blog",
            source_name="OpenAI",
        )
        result = deduplicate([hn_item, blog_item], _empty_history())
        assert len(result) == 1
        assert result[0].source == "blog"  # 原始来源优先

    def test_case2_blog_first(self):
        """blog 先出现时也应保留 blog"""
        blog_item = _make_item(
            title="Testing ads in ChatGPT",
            url="https://openai.com/index/testing-ads-in-chatgpt",
            source="blog",
            source_name="OpenAI",
        )
        hn_item = _make_item(
            title="Testing Ads in ChatGPT",
            url="https://openai.com/index/testing-ads-in-chatgpt/",
            source="hackernews",
            source_name="Hacker News",
        )
        result = deduplicate([blog_item, hn_item], _empty_history())
        assert len(result) == 1
        assert result[0].source == "blog"

    def test_title_dedup_different_urls(self):
        """标题去重：完全不同的 URL 但标题相同"""
        item1 = _make_item(
            title="Some Breaking AI News Title Here",
            url="https://site-a.com/news/12345",
            source="blog",
            source_name="Site A",
        )
        item2 = _make_item(
            title="Some Breaking AI News Title Here",
            url="https://site-b.com/posts/67890",
            source="hackernews",
            source_name="Hacker News",
        )
        result = deduplicate([item1, item2], _empty_history())
        assert len(result) == 1
        assert result[0].source == "blog"  # blog priority < hackernews

    def test_short_title_no_false_dedup(self):
        """短标题不应触发标题去重（防误匹配）"""
        item1 = _make_item(
            title="GPT-5",
            url="https://example.com/a",
            source="blog",
        )
        item2 = _make_item(
            title="GPT-5",
            url="https://example.com/b",
            source="hackernews",
        )
        result = deduplicate([item1, item2], _empty_history())
        # Short title ("gpt 5" = 5 chars) should NOT trigger title dedup,
        # but URL normalization also won't match → both should remain
        assert len(result) == 2

    def test_no_duplicates(self):
        """无重复时全部保留"""
        items = [
            _make_item(title="News A", url="https://a.com/1", source="blog"),
            _make_item(title="News B", url="https://b.com/2", source="arxiv"),
            _make_item(title="News C", url="https://c.com/3", source="hackernews"),
        ]
        result = deduplicate(items, _empty_history())
        assert len(result) == 3

    def test_history_url_filter(self):
        """历史 URL 过滤"""
        item = _make_item(url="https://example.com/old")
        history = {"urls": {"https://example.com/old"}, "canonical_keys": set()}
        result = deduplicate([item], history)
        assert len(result) == 0

    def test_history_normalized_url_filter(self):
        """历史 URL 标准化过滤（http vs https）"""
        item = _make_item(url="https://example.com/old")
        history = {"urls": {"http://example.com/old"}, "canonical_keys": set()}
        result = deduplicate([item], history)
        assert len(result) == 0

    def test_history_canonical_key_filter(self):
        """历史 canonical key 过滤"""
        item = _make_item(
            url="https://huggingface.co/papers/2602.06570",
            source="hf_papers",
        )
        history = {"urls": set(), "canonical_keys": {"arxiv:2602.06570"}}
        result = deduplicate([item], history)
        assert len(result) == 0

    def test_empty_input(self):
        """空输入"""
        result = deduplicate([], _empty_history())
        assert len(result) == 0

    def test_source_priority_values(self):
        """来源优先级配置合理性"""
        # Original sources should have lower (better) priority
        assert SOURCE_PRIORITY["arxiv"] < SOURCE_PRIORITY["hf_papers"]
        assert SOURCE_PRIORITY["blog"] < SOURCE_PRIORITY["hackernews"]
        assert SOURCE_PRIORITY["github"] < SOURCE_PRIORITY["github_trending"]

    def test_three_sources_same_paper(self):
        """同一论文出现在 3 个来源（arxiv + hf_papers + reddit title match）"""
        arxiv_item = _make_item(
            title="Amazing New LLM Research Paper Title",
            url="http://arxiv.org/abs/2602.99999v1",
            source="arxiv",
            source_name="CL",
        )
        hf_item = _make_item(
            title="Amazing New LLM Research Paper Title",
            url="https://huggingface.co/papers/2602.99999",
            source="hf_papers",
            source_name="HF Daily Papers",
        )
        reddit_item = _make_item(
            title="Amazing New LLM Research Paper Title",
            url="https://reddit.com/r/MachineLearning/comments/abc123",
            source="reddit",
            source_name="r/MachineLearning",
        )
        result = deduplicate([hf_item, reddit_item, arxiv_item], _empty_history())
        assert len(result) == 1
        assert result[0].source == "arxiv"  # 最高优先级
