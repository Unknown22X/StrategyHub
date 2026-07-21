"""Localhost client used by the Paper Trading desktop interface."""

from typing import Any

import httpx

from rangebot.domain.application import ApplicationSettings, ApplicationSettingsUpdate
from rangebot.domain.runtime import RuntimeState


class EngineClient:
    """Calls only the local RangeBot engine; it has no exchange authority."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def fetch_runtime_state(self) -> RuntimeState:
        return RuntimeState.model_validate(self.get("/v1/runtime-state"))

    def fetch_application_settings(self) -> ApplicationSettings:
        return ApplicationSettings.model_validate(self.get("/v1/settings"))

    def save_application_settings(
        self, settings: ApplicationSettingsUpdate
    ) -> ApplicationSettings:
        return ApplicationSettings.model_validate(
            self.put("/v1/settings", settings.model_dump(mode="json"))
        )

    def get(self, path: str, params: dict[str, str] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        return self._request("POST", path, payload)

    def put(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("PUT", path, payload)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        response = httpx.request(
            method,
            f"{self._base_url}{path}",
            json=payload,
            params=params,
            timeout=3.0,
        )
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return response.json()
