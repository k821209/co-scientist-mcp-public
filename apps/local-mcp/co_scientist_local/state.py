"""Per-session state: the active project + the backend it writes to.

The local MCP is scoped to **one project** at a time. The project_id is set
at process start from the downloaded MCP bundle (which carries the project's
API key) and never changes during the session. Every tool call uses the
same project_id.

`owner_uid` is kept on State as the project's owning user — useful for owner-
check operations and for the Cloud Function key-exchange flow that mints a
custom token carrying `{ uid, project_id }`. Tools should NOT use uid for
path construction — that's what project_path() is for.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .backends import Backend

if TYPE_CHECKING:
    from .exporters import PandocExecutor
    from .image_gen import ImageGenerator
    from .ssh import RsyncExecutor, SSHExecutor

# Public dashboard host (Firebase Hosting). Overridable for emulator/testing.
DASHBOARD_BASE_URL = os.environ.get(
    "CO_SCIENTIST_DASHBOARD_URL", "https://co-scientist-5af1a.web.app",
).rstrip("/")


@dataclass
class State:
    project_id: str
    owner_uid: str
    backend: Backend
    ssh: "SSHExecutor | None" = None
    rsync: "RsyncExecutor | None" = None
    pandoc: "PandocExecutor | None" = None
    image_gen: "ImageGenerator | None" = None

    def project_path(self, *parts: str) -> str:
        """Build a path rooted at the active project.

        Example:
            state.project_path("papers", "rice-evo")
            -> "projects/abc123/papers/rice-evo"
        """
        return "/".join(("projects", self.project_id, *parts))

    def dashboard_url(self, *parts: str) -> str:
        """Clickable dashboard URL rooted at the active project.

        Example:
            state.dashboard_url("papers", "rice-evo")
            -> "https://…web.app/projects/abc123/papers/rice-evo"
        """
        suffix = "/".join(("projects", self.project_id, *parts))
        return f"{DASHBOARD_BASE_URL}/{suffix}"

    def require_ssh(self) -> "SSHExecutor":
        if self.ssh is None:
            from .ssh import RealSSHExecutor
            self.ssh = RealSSHExecutor()
        return self.ssh

    def require_rsync(self) -> "RsyncExecutor":
        if self.rsync is None:
            from .ssh import RealRsyncExecutor
            self.rsync = RealRsyncExecutor()
        return self.rsync

    def require_pandoc(self) -> "PandocExecutor":
        if self.pandoc is None:
            from .exporters import RealPandocExecutor
            self.pandoc = RealPandocExecutor()
        return self.pandoc

    def require_image_gen(self) -> "ImageGenerator":
        if self.image_gen is None:
            raise RuntimeError(
                "no image generator configured. Set up your "
                "GEMINI_API_KEY (free) or subscribe (cloud-routed) "
                "and configure ~/.co-scientist/projects/<pid>.toml."
            )
        return self.image_gen
