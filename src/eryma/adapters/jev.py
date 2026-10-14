"""Optional Jev integration for the documented OpenRouter Decisions API."""
import os
from ._shared import optional_module, normalize
from .decisions_api import DecisionsAPIFormat
from .errors import (AuthenticationError, NetworkError,
                     AdapterTimeoutError, InvalidOutputError, UnsupportedModelError,
                     UnsupportedCriteriaError)


class JevAdapter:
    def __init__(self, *, model: str, api_key: str | None = None,
                 endpoint: str = "https://openrouter.ai/api/alpha/decisions",
                 api_key_env: str = "OPENROUTER_API_KEY", timeout: float = 60,
                 send_trusted_references: bool = False, transport=None):
        if type(send_trusted_references) is not bool:
            raise ValueError("send_trusted_references must be a boolean")
        if not isinstance(api_key_env, str) or not api_key_env:
            raise ValueError("api_key_env must be a nonempty variable name")
        key = api_key if api_key is not None else os.environ.get(api_key_env)
        if not isinstance(key, str) or not key.strip():
            raise AuthenticationError()
        try:
            self._formatter = DecisionsAPIFormat(model=model)
        except ValueError:
            raise UnsupportedModelError() from None
        self._send_references = send_trusted_references
        self._httpx = optional_module("httpx", "jev")
        from .http import HTTPDecisionModel
        self._client = HTTPDecisionModel(endpoint=endpoint, api_key=key, timeout=timeout,
            request_builder=self._formatter.build_request,
            response_parser=self._formatter.parse_response, transport=transport)
        self._closed = False

    def evaluate(self, request):
        if self._closed:
            raise NetworkError()
        if request.trusted_context.get("references") and not self._send_references:
            raise UnsupportedCriteriaError()
        payload = self._formatter.build_request(request)
        try:
            # Reuse the generic client's configured TLS, authentication and lifecycle.
            # Handle statuses here to preserve actionable native-adapter error types.
            response = self._client._client.post(self._client._endpoint, json=payload)
        except self._httpx.TimeoutException:
            raise AdapterTimeoutError() from None
        except Exception:
            raise NetworkError() from None
        if response.status_code in (401, 403):
            raise AuthenticationError()
        if response.status_code == 404:
            raise UnsupportedModelError()
        if response.status_code in (400, 422):
            raise UnsupportedCriteriaError()
        if not 200 <= response.status_code < 300:
            raise NetworkError()
        try:
            data = response.json()
        except Exception:
            raise InvalidOutputError() from None
        return normalize(data, request, self._formatter)

    def close(self):
        if not self._closed:
            self._client.close()
            self._closed = True

    def __enter__(self):
        if self._closed:
            raise NetworkError()
        return self

    def __exit__(self, *args):
        self.close()
