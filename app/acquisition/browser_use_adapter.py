from __future__ import annotations

from .base import AcquisitionError
from .models import AcquisitionRequest, AcquisitionResult


class BrowserUseAdapter:
    """Optional browser-agent adapter.

    It is intentionally opt-in because Browser Use may require a configured model/provider
    for agent-driven interactions. It is not used to bypass CAPTCHA, authentication,
    robots policies, or other access controls.
    """

    async def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        try:
            import browser_use  # noqa: F401
        except ImportError as exc:
            raise AcquisitionError(
                "Browser Use is not installed in this runtime. "
                "Use the optional browser environment."
            ) from exc
        raise AcquisitionError(
            "Browser Use is installed but no agent/model is configured. "
            "Use Crawl4AI for normal pages; configure Browser Use explicitly for interactive pages."
        )
