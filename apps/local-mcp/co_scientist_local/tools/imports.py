"""Document import: convert an existing manuscript (docx / pdf / etc.)
into markdown so the agent can split it into paper sections.

`import_document` does the deterministic conversion:
  - docx / odt / rtf / html / tex / epub / md → pandoc → markdown,
    with --extract-media so embedded images land on disk
  - pdf → pypdf text extraction (LOSSY — PDF is a layout format with
    no section structure; figures/tables don't survive)

The MCP only converts. Splitting the markdown into canonical sections
(abstract / introduction / methods / …) is the agent's job — that's an
LLM task, and the /paper-import skill drives it.
"""
from __future__ import annotations

import pathlib
import subprocess

# Formats pandoc reads well enough to preserve structure.
_PANDOC_FORMATS = {
    ".docx": "docx",
    ".odt": "odt",
    ".rtf": "rtf",
    ".html": "html",
    ".htm": "html",
    ".tex": "latex",
    ".latex": "latex",
    ".epub": "epub",
    ".md": "markdown",
    ".markdown": "markdown",
}


def import_document(
    state,  # noqa: ARG001 — network/FS only; kept for signature symmetry
    *,
    local_path: str,
    extract_media_to: str | None = None,
) -> dict:
    """Convert a manuscript file to markdown.

    Returns:
        {
          "source_format": "docx" | "pdf" | …,
          "markdown": "<converted text>",
          "media": ["path/to/img1.png", …],   # extracted images (docx etc.)
          "warnings": ["…"],                  # lossy-conversion notes
          "char_count": int,
        }
    """
    src = pathlib.Path(local_path).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"file not found: {src}")
    ext = src.suffix.lower()
    warnings: list[str] = []

    if ext == ".pdf":
        markdown = _pdf_to_text(src)
        warnings.append(
            "PDF import is lossy — PDF has no section structure, and "
            "figures/tables are NOT extracted. The agent must reconstruct "
            "sections from the flat text. For best results, import the "
            "original .docx instead."
        )
        return {
            "source_format": "pdf",
            "markdown": markdown,
            "media": [],
            "warnings": warnings,
            "char_count": len(markdown),
        }

    pandoc_fmt = _PANDOC_FORMATS.get(ext)
    if pandoc_fmt is None:
        raise ValueError(
            f"unsupported import format: {ext!r}. Supported: "
            f"{sorted(_PANDOC_FORMATS) + ['.pdf']}"
        )

    markdown, media = _pandoc_to_markdown(src, pandoc_fmt, extract_media_to)
    if not media and ext in (".docx", ".odt"):
        warnings.append(
            "No embedded images found — if the source had figures, they "
            "may need to be re-added via add_figure / generate_image."
        )
    return {
        "source_format": pandoc_fmt,
        "markdown": markdown,
        "media": media,
        "warnings": warnings,
        "char_count": len(markdown),
    }


def _pandoc_to_markdown(
    src: pathlib.Path,
    pandoc_fmt: str,
    extract_media_to: str | None,
) -> tuple[str, list[str]]:
    """Run pandoc <src> -f <fmt> -t markdown. Extract embedded media into
    `extract_media_to` (defaults to a sibling `<stem>-media/` dir)."""
    media_dir = pathlib.Path(
        extract_media_to or (src.parent / f"{src.stem}-media")
    ).expanduser()
    args = [
        "pandoc", str(src),
        "-f", pandoc_fmt,
        "-t", "markdown-raw_html",   # drop raw HTML noise from docx
        "--wrap=none",
        f"--extract-media={media_dir}",
    ]
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=120,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "pandoc not found — install it (brew install pandoc / "
            "apt install pandoc). It's the same dependency /paper-export needs."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("pandoc conversion timed out (120s)") from e
    if proc.returncode != 0:
        raise RuntimeError(
            f"pandoc failed (rc={proc.returncode}): {proc.stderr[:400]}"
        )
    media: list[str] = []
    if media_dir.is_dir():
        media = sorted(
            str(p) for p in media_dir.rglob("*") if p.is_file()
        )
    return proc.stdout, media


def _pdf_to_text(src: pathlib.Path) -> str:
    """Extract text from a PDF, page by page, via pypdf. Lossy."""
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "pypdf not installed — reinstall the package: "
            "pip install -e ~/co-scientist-mcp-public/apps/local-mcp"
        ) from e
    reader = PdfReader(str(src))
    parts: list[str] = []
    for page in reader.pages:
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        if txt.strip():
            parts.append(txt.strip())
    return "\n\n".join(parts)
