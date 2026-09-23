"""Reach a Jev deployment that serves System One at a different path.

The SDK posts to a fixed `/v1/systemone`, but the same request and response
bodies are served elsewhere by hosts that proxy Jev -- OpenRouter's Decisions
API at `/api/alpha/decisions`, for example. Rewriting the path in the transport
keeps the SDK's own validation, retries, and error types.
"""
import httpx2


class PathRewriteTransport(httpx2.BaseTransport):
    """Send every request to `path` on the host the base URL already chose."""

    def __init__(self, path, inner=None):
        if not isinstance(path, str) or not path.startswith("/"):
            raise ValueError("path must be an absolute request path")
        self.path = path
        self.inner = inner if inner is not None else httpx2.HTTPTransport()

    def handle_request(self, request):
        request.url = request.url.copy_with(path=self.path)
        return self.inner.handle_request(request)

    def close(self):
        self.inner.close()
