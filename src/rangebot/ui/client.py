"""Read-only client for the engine's localhost lifecycle contract."""

import httpx

from rangebot.domain.runtime import RuntimeState


class EngineClient:
    """Fetches fresh engine snapshots; it has no trading or exchange authority."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def fetch_runtime_state(self) -> RuntimeState:
        response = httpx.get(f"{self._base_url}/v1/runtime-state", timeout=1.0)
        response.raise_for_status()
        return RuntimeState.model_validate(response.json())
