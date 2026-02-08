"""Base collector abstract class.

所有 collector 的统一基类，提供标准化接口和注册机制。
All collectors inherit from BaseCollector for a unified interface.
"""

import logging
from abc import ABC, abstractmethod

from ..models import NewsItem

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """Abstract base class for all news collectors.

    每个 collector 继承此基类，配置通过 __init__ 注入。
    统一接口：collect(keywords) -> list[NewsItem]。
    """

    name: str = ""  # collector 标识，如 "arxiv", "hf_models"
    enabled: bool = True

    @abstractmethod
    def collect(self, keywords: list[str]) -> list[NewsItem]:
        """Collect news items from the source.

        Args:
            keywords: Keywords to filter relevant content.
                关键词列表，用于过滤相关内容。

        Returns:
            List of collected NewsItem.
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} enabled={self.enabled}>"
