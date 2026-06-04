"""Image-generation executor abstraction.

Three production backends:
- **LocalGeminiImageGenerator** — free tier, Google Gemini; uses the user's
  own GEMINI_API_KEY via google-generativeai.
- **LocalOpenAIImageGenerator** — free tier, OpenAI gpt-image-2; uses the
  user's own OPENAI_API_KEY via the OpenAI REST API (no SDK dep).
- **CloudFunctionImageGenerator** — subscribed tier; HTTPS POSTs to the
  Firebase Cloud Function at /generate_image, which validates the user's
  Firebase ID token, checks plan + monthly quota in Firestore, calls the
  configured provider with the server's key, returns PNG bytes.

Architecture note: this is the ONLY server-side AI surface in the system.
Text/LLM agent work stays in Claude Code on the user's machine. See
~/.claude/projects/.../memory/architecture_decisions.md.
"""
from __future__ import annotations

from typing import Callable, Protocol


class QuotaExceeded(Exception):
    """Raised when the Cloud Function returns 429 (monthly image quota hit)."""


class ImageGenerator(Protocol):
    def generate(
        self,
        *,
        prompt: str,
        aspect_ratio: str = "1:1",
        model: str = "gpt-image-2",
        quality: str | None = None,
    ) -> bytes:
        """Generate an image. Returns the PNG (or other format) bytes.

        `quality` (gpt-image: low/medium/high/auto) is passed to the provider
        when set; None leaves the provider default.
        """
        ...


class LocalGeminiImageGenerator:
    """Free-tier: caller-supplied GEMINI_API_KEY, direct Gemini call.

    Lazy-imports google-generativeai so the package stays optional.
    """

    def __init__(self, *, api_key: str) -> None:
        if not api_key:
            raise ValueError("api_key is required for LocalGeminiImageGenerator")
        self._api_key = api_key

    def generate(
        self,
        *,
        prompt: str,
        aspect_ratio: str = "1:1",
        model: str = "imagen-3",
        quality: str | None = None,
    ) -> bytes:
        # Gemini path ignores quality (no equivalent knob).
        # Lazy import — pip extra `gemini` pulls google-generativeai
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "google-generativeai not installed. "
                "pip install google-generativeai"
            ) from e
        genai.configure(api_key=self._api_key)
        gen_model = genai.GenerativeModel(model)
        response = gen_model.generate_content(prompt)  # pragma: no cover
        # Extract PNG bytes from response. Shape varies by SDK version — the
        # caller should treat this as best-effort and fall back gracefully.
        for part in response.parts:
            if hasattr(part, "inline_data") and getattr(part.inline_data, "data", None):
                return part.inline_data.data
        raise RuntimeError("no image bytes in Gemini response")


class LocalOpenAIImageGenerator:
    """Free-tier OpenAI: caller-supplied OPENAI_API_KEY, direct REST call.

    Uses the OpenAI Images API (gpt-image-2; same /v1/images/generations
    endpoint as gpt-image-1). Returns raw PNG bytes. Implemented with stdlib
    `urllib` to avoid an SDK dependency.
    """

    # gpt-image-2 supported sizes (same as gpt-image-1). Map common aspect ratios.
    SIZE_MAP = {
        "1:1": "1024x1024",
        "square": "1024x1024",
        "16:9": "1536x1024",
        "3:2": "1536x1024",
        "landscape": "1536x1024",
        "9:16": "1024x1536",
        "2:3": "1024x1536",
        "portrait": "1024x1536",
    }

    URL = "https://api.openai.com/v1/images/generations"

    def __init__(self, *, api_key: str, default_model: str = "gpt-image-2") -> None:
        if not api_key:
            raise ValueError("api_key is required for LocalOpenAIImageGenerator")
        self._api_key = api_key
        self._default_model = default_model

    def generate(
        self,
        *,
        prompt: str,
        aspect_ratio: str = "1:1",
        model: str = "gpt-image-2",
        quality: str | None = None,
    ) -> bytes:
        import base64
        import json as _json
        import urllib.error
        import urllib.request

        size = self.SIZE_MAP.get(aspect_ratio, "1024x1024")
        # gpt-image-2 always returns b64_json (no response_format param needed).
        payload: dict = {
            "model": model or self._default_model,
            "prompt": prompt,
            "size": size,
            "n": 1,
        }
        if quality:
            payload["quality"] = quality
        body = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.URL,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = _json.loads(resp.read())
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"OpenAI HTTP {e.code}: {err_body}") from e

        item = (payload.get("data") or [{}])[0]
        if "b64_json" in item and item["b64_json"]:
            return base64.b64decode(item["b64_json"])
        if "url" in item and item["url"]:
            # Some models return URL instead of inline bytes — fetch it.
            with urllib.request.urlopen(item["url"], timeout=120) as r:
                return r.read()
        raise RuntimeError(f"OpenAI response had no image data: {payload!r}")


class CloudFunctionImageGenerator:
    """Subscribed-tier (Pro+): HTTPS POST to the Firebase Cloud Function
    /generate_image. The function picks the provider (openai default, gemini
    optional) — we just pass prompt + aspect ratio.

    Raises:
        QuotaExceeded — server returned 429 (monthly quota hit)
        PermissionError — server returned 403 (free plan or disabled account)
        RuntimeError — other transport / provider errors
    """

    def __init__(
        self,
        *,
        function_url: str,
        get_id_token: Callable[[], str],
    ) -> None:
        self._url = function_url
        self._get_id_token = get_id_token

    def generate(
        self,
        *,
        prompt: str,
        aspect_ratio: str = "1:1",
        model: str | None = None,
        quality: str | None = None,
    ) -> bytes:
        import json as _json
        import urllib.error
        import urllib.request

        token = self._get_id_token()
        payload: dict = {"prompt": prompt, "aspect_ratio": aspect_ratio}
        if model:
            payload["model"] = model
        if quality:
            payload["quality"] = quality

        req = urllib.request.Request(
            self._url,
            data=_json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            # Match the Cloud Function's 300s ceiling — image gen is slow.
            with urllib.request.urlopen(req, timeout=310) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            try:
                detail = _json.loads(err_body)
            except Exception:
                detail = {"error": err_body}
            if e.code == 429:
                msg = detail.get("message") or detail.get("error") or "quota exceeded"
                raise QuotaExceeded(msg) from e
            if e.code == 403:
                msg = detail.get("error") or "forbidden"
                raise PermissionError(msg) from e
            raise RuntimeError(f"Cloud Function HTTP {e.code}: {err_body}") from e


class FakeImageGenerator:
    """Test image generator.

    Records every call and returns canned PNG bytes. Tests verify both that
    the right arguments were passed AND that the bytes end up in Storage.
    """

    def __init__(self, *, png_bytes: bytes = b"\x89PNG_FAKE") -> None:
        self.calls: list[dict] = []
        self._png = png_bytes
        self._quota_exceeded = False

    def trigger_quota_exceeded(self) -> None:
        """Make subsequent calls raise QuotaExceeded."""
        self._quota_exceeded = True

    def generate(
        self,
        *,
        prompt: str,
        aspect_ratio: str = "1:1",
        model: str = "gpt-image-2",
        quality: str | None = None,
    ) -> bytes:
        if self._quota_exceeded:
            raise QuotaExceeded("test-quota-exceeded")
        self.calls.append({
            "prompt": prompt, "aspect_ratio": aspect_ratio, "model": model,
            "quality": quality,
        })
        return self._png
