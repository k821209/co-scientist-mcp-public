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


def _multipart_body(fields: dict, files: dict) -> tuple[bytes, str]:
    """Encode multipart/form-data. `fields`: {name: value}. `files`:
    {name: (filename, bytes, content_type)}. Returns (body, content_type)."""
    import uuid as _uuid
    boundary = "----coScientist" + _uuid.uuid4().hex
    out: list[bytes] = []
    for name, val in fields.items():
        if val is None:
            continue
        out += [f"--{boundary}".encode(),
                f'Content-Disposition: form-data; name="{name}"'.encode(),
                b"", str(val).encode()]
    for name, spec in files.items():
        if not spec or spec[1] is None:
            continue
        fname, data, ctype = spec
        out += [f"--{boundary}".encode(),
                f'Content-Disposition: form-data; name="{name}"; filename="{fname}"'.encode(),
                f"Content-Type: {ctype}".encode(), b"", data]
    out += [f"--{boundary}--".encode(), b""]
    return b"\r\n".join(out), f"multipart/form-data; boundary={boundary}"


def _openai_images_edit(*, api_key: str, prompt: str, image: bytes,
                        mask: bytes | None, size: str, model: str,
                        quality: str | None = None, timeout: int = 290) -> bytes:
    """POST to OpenAI /v1/images/edits (gpt-image edit / inpaint). Returns PNG
    bytes. Shared by the local direct-key path and mirrored in the Cloud
    Function."""
    import base64
    import json as _json
    import urllib.request
    fields: dict = {"model": model or "gpt-image-2", "prompt": prompt,
                    "size": size, "n": "1"}
    if quality:
        fields["quality"] = quality
    files = {"image": ("image.png", image, "image/png"),
             "mask": ("mask.png", mask, "image/png") if mask else None}
    body, ctype = _multipart_body(fields, {k: v for k, v in files.items() if v})
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/edits", data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = _json.loads(resp.read())
    item = (payload.get("data") or [{}])[0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):
        with urllib.request.urlopen(item["url"], timeout=120) as r:
            return r.read()
    raise RuntimeError(f"OpenAI edit response had no image data: {payload!r}")


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

    def edit(
        self,
        *,
        prompt: str,
        image: bytes,
        mask: bytes | None = None,
        aspect_ratio: str = "1:1",
        model: str = "gpt-image-2",
        quality: str | None = None,
    ) -> bytes:
        """Edit `image` (PNG bytes) guided by `prompt`, optionally within the
        transparent area of `mask`. Returns PNG bytes. Use for character-
        consistency (keep the face, change outfit/pose), outpaint, object
        removal. Not every backend supports it (Gemini free tier does not)."""
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

    def edit(self, *, prompt, image, mask=None, aspect_ratio="1:1",
             model="imagen-3", quality=None) -> bytes:
        raise RuntimeError(
            "image editing (reference image) is not supported on the Gemini "
            "free tier — set OPENAI_API_KEY for the OpenAI edit path, or use a "
            "Pro subscription (Cloud Function)")


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

    def edit(self, *, prompt, image, mask=None, aspect_ratio="1:1",
             model="gpt-image-2", quality=None) -> bytes:
        import urllib.error
        size = self.SIZE_MAP.get(aspect_ratio, "1024x1024")
        try:
            return _openai_images_edit(
                api_key=self._api_key, prompt=prompt, image=image, mask=mask,
                size=size, model=model or self._default_model, quality=quality,
                timeout=290)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"OpenAI edit HTTP {e.code}: {err_body}") from e


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

    def edit(self, *, prompt, image, mask=None, aspect_ratio="1:1",
             model=None, quality=None) -> bytes:
        import base64
        import json as _json
        import urllib.error
        import urllib.request

        token = self._get_id_token()
        payload: dict = {
            "prompt": prompt, "aspect_ratio": aspect_ratio,
            "input_image": base64.b64encode(image).decode("ascii"),
        }
        if mask:
            payload["mask"] = base64.b64encode(mask).decode("ascii")
        if model:
            payload["model"] = model
        if quality:
            payload["quality"] = quality
        req = urllib.request.Request(
            self._url, data=_json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=310) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            try:
                detail = _json.loads(err_body)
            except Exception:
                detail = {"error": err_body}
            if e.code == 429:
                raise QuotaExceeded(detail.get("message") or "quota exceeded") from e
            if e.code == 403:
                raise PermissionError(detail.get("error") or "forbidden") from e
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

    def edit(self, *, prompt, image, mask=None, aspect_ratio="1:1",
             model="gpt-image-2", quality=None) -> bytes:
        if self._quota_exceeded:
            raise QuotaExceeded("test-quota-exceeded")
        self.calls.append({
            "op": "edit", "prompt": prompt, "aspect_ratio": aspect_ratio,
            "model": model, "quality": quality,
            "image_bytes": len(image or b""), "has_mask": mask is not None,
        })
        return self._png
