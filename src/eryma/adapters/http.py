"""Optional provider-neutral HTTP adapter with developer-supplied wire translations."""
from __future__ import annotations
from urllib.parse import urlparse
try:
    import httpx
except ImportError:
    raise ImportError("Install eryma[http] to use the HTTP adapter") from None
from ..types import EvaluationRequest, ScoreDistribution, finite_number


class ProviderError(RuntimeError):
    """Sanitized provider failure without request bodies or credentials."""


class HTTPDecisionModel:
    def __init__(self, *, endpoint: str, request_builder, response_parser,
                 api_key: str | None = None, headers: dict[str, str] | None = None, timeout: float = 60,
                 transport: httpx.BaseTransport | None = None):
        if api_key is not None and (not isinstance(api_key, str) or not api_key.strip()):
            raise ValueError("api_key must be non-empty")
        if not callable(request_builder) or not callable(response_parser):
            raise ValueError("Supply callable request_builder and response_parser")
        if not isinstance(endpoint, str):
            raise ValueError("endpoint must be an HTTPS URL")
        url = urlparse(endpoint)
        if url.scheme != "https" or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError("endpoint must be HTTPS without credentials, query or fragment")
        timeout = finite_number(timeout)
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        auth_headers = dict(headers or {})
        if api_key is not None:
            if any(k.lower() == 'authorization' for k in auth_headers):
                raise ValueError("Supply either api_key or a custom Authorization header")
            auth_headers['Authorization'] = f'Bearer {api_key}'
        self._endpoint = endpoint
        self._request_builder = request_builder
        self._response_parser = response_parser
        self._client = httpx.Client(timeout=timeout, headers=auth_headers,
                                    transport=transport, follow_redirects=False)

    def _post(self, payload):
        # No automatic retries: a timed-out paid call may already have executed.
        try:
            response = self._client.post(self._endpoint, json=payload)
            if not 200 <= response.status_code < 300:
                raise ProviderError(f"Provider HTTP {response.status_code}")
            data = response.json()
            if not isinstance(data, dict):
                raise ProviderError("Invalid provider response")
            return data
        except (httpx.HTTPError, ValueError):
            raise ProviderError("Provider transport or response error") from None

    def evaluate(self, request: EvaluationRequest) -> dict[str, ScoreDistribution]:
        try:
            payload = self._request_builder(request)
            if not isinstance(payload, dict):
                raise ValueError()
            return self._response_parser(self._post(payload), request)
        except Exception:
            raise ProviderError("Decision provider evaluation failed") from None

    def close(self): self._client.close()
    def __enter__(self): return self
    def __exit__(self, *args): self.close()
