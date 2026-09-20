from .base import AcquisitionError
from .browser_use_adapter import BrowserUseAdapter
from .crawl4ai_adapter import Crawl4AIAdapter
from .engine import AcquisitionEngine
from .markitdown_adapter import MarkItDownAdapter
from .models import AcquisitionKind, AcquisitionRequest, AcquisitionResult


def default_engine(*, enable_browser: bool = False) -> AcquisitionEngine:
    return AcquisitionEngine(
        web=Crawl4AIAdapter(),
        files=MarkItDownAdapter(),
        browser=BrowserUseAdapter() if enable_browser else None,
    )


__all__ = [
    "AcquisitionEngine",
    "AcquisitionError",
    "AcquisitionKind",
    "AcquisitionRequest",
    "AcquisitionResult",
    "BrowserUseAdapter",
    "Crawl4AIAdapter",
    "MarkItDownAdapter",
    "default_engine",
]
