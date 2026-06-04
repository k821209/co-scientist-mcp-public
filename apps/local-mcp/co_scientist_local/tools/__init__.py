"""Tool functions for the local MCP. Each is a plain Python callable taking
`State` as first argument so unit tests can hit them without MCP transport."""

from . import (
    analyses,
    exports,
    figures,
    images,
    papers,
    references,
    reviews,
    runs,
    sections,
    servers,
    ssh_ops,
    tables,
)

__all__ = [
    "papers", "sections", "reviews",
    "figures", "tables", "references",
    "analyses", "runs", "servers", "ssh_ops",
    "exports", "images",
]
