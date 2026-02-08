"""HuggingFace Models collector.

Tracks trending and recently updated models from specified organizations.
HuggingFace Hub API 免费，无需 API Key（公开模型）。

API: https://huggingface.co/api/models
覆盖中国大模型公司：DeepSeek, Qwen, GLM, Kimi, MiniMax, StepFun 等。
"""

import logging
from datetime import datetime, timezone

import httpx

from ..models import NewsItem
from .base import BaseCollector

logger = logging.getLogger(__name__)

HF_MODELS_API = "https://huggingface.co/api/models"


class HfModelsCollector(BaseCollector):
    """HuggingFace Models collector.

    追踪 HuggingFace Hub 上指定组织的新模型发布和热门模型。
    Track new and trending models from specified HF organizations.
    """

    name = "hf_models"

    def __init__(
        self,
        orgs: list[str] | None = None,
        limit: int = 50,
    ) -> None:
        self.orgs = orgs or [
            "deepseek-ai",  # DeepSeek
            "Qwen",  # 阿里 Qwen
            "zai-org",  # 智谱 GLM (Z.ai)
            "MiniMaxAI",  # MiniMax
            "stepfun-ai",  # 阶跃星辰
            "meta-llama",  # Meta LLaMA
            "mistralai",  # Mistral
            "google",  # Google Gemma
            "microsoft",  # Microsoft Phi
            "openai",  # OpenAI
        ]
        self.limit = limit

    def _fetch_org_models(
        self, client: httpx.Client, org: str
    ) -> list[dict]:
        """Fetch recently updated models for a given HF organization.

        按最近更新排序获取指定组织的模型列表。
        """
        try:
            resp = client.get(
                HF_MODELS_API,
                params={
                    "author": org,
                    "sort": "lastModified",
                    "direction": -1,
                    "limit": 10,
                },
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.warning("Failed to fetch HF models for org: %s", org)
            return []

    def _fetch_trending(self, client: httpx.Client) -> list[dict]:
        """Fetch globally popular models (sorted by likes).

        获取全局热门模型（按 likes 排序，HF API 不支持 sort=trending）。
        """
        try:
            resp = client.get(
                HF_MODELS_API,
                params={
                    "sort": "likes",
                    "direction": -1,
                    "limit": self.limit,
                    "pipeline_tag": "text-generation",
                },
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.warning("Failed to fetch trending HF models")
            return []

    def collect(self, keywords: list[str]) -> list[NewsItem]:
        items: list[NewsItem] = []
        seen_ids: set[str] = set()

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            # 1. Fetch models from each tracked org / 按组织拉取
            for org in self.orgs:
                logger.info("Fetching HF models for org: %s", org)
                models = self._fetch_org_models(client, org)
                for model in models:
                    model_id = model.get("id", "")
                    if not model_id or model_id in seen_ids:
                        continue
                    seen_ids.add(model_id)

                    item = self._model_to_item(model)
                    if item:
                        items.append(item)

            # 2. Fetch globally trending text-generation models / 全局热门
            logger.info("Fetching trending HF text-generation models")
            trending = self._fetch_trending(client)
            for model in trending:
                model_id = model.get("id", "")
                if not model_id or model_id in seen_ids:
                    continue
                seen_ids.add(model_id)

                item = self._model_to_item(model)
                if item:
                    items.append(item)

        logger.info("HF Models: collected %d models", len(items))
        return items

    @staticmethod
    def _model_to_item(model: dict) -> NewsItem | None:
        """Convert a HF API model dict to NewsItem.

        将 HF API 返回的模型字典转换为 NewsItem。
        """
        model_id = model.get("id", "")
        if not model_id:
            return None

        # Build description from available metadata
        # 从可用元数据构建描述
        pipeline_tag = model.get("pipeline_tag", "")
        tags = model.get("tags", [])
        downloads = model.get("downloads", 0)
        likes = model.get("likes", 0)
        last_modified = model.get("lastModified", "")

        # Extract org name / 提取组织名
        org = model_id.split("/")[0] if "/" in model_id else ""

        content_parts = []
        if pipeline_tag:
            content_parts.append(f"Pipeline: {pipeline_tag}")
        if downloads:
            content_parts.append(f"Downloads: {downloads:,}")
        if likes:
            content_parts.append(f"Likes: {likes}")
        if tags:
            # Show first few relevant tags
            relevant_tags = [
                t for t in tags[:10]
                if not t.startswith("arxiv:") and t != pipeline_tag
            ]
            if relevant_tags:
                content_parts.append(f"Tags: {', '.join(relevant_tags[:5])}")

        published_at = None
        if last_modified:
            try:
                published_at = datetime.fromisoformat(
                    last_modified.replace("Z", "+00:00")
                )
            except ValueError:
                pass

        return NewsItem(
            title=f"[HF Model] {model_id}",
            url=f"https://huggingface.co/{model_id}",
            source="hf_models",
            source_name=org or "HuggingFace",
            content=" | ".join(content_parts),
            score=float(likes),
            published_at=published_at,
        )
