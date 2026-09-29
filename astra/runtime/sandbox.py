from __future__ import annotations

import os
import tempfile
import shutil
from contextlib import contextmanager
from typing import Optional
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SandboxConfig:
    """Sandbox isolation configuration."""
    allow_network: bool = False
    allow_filesystem_write: bool = False
    max_files: int = 100
    max_file_size_mb: int = 10
    allowed_paths: Optional[list[str]] = None
    blocked_paths: Optional[list[str]] = None

    def __post_init__(self):
        if self.allowed_paths is None:
            self.allowed_paths = []
        if self.blocked_paths is None:
            self.blocked_paths = []


class ExecutionSandbox:
    """Filesystem and network isolation for task execution."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig()
        self._temp_dir: Optional[str] = None
        self._original_cwd: Optional[str] = None

    def _is_path_allowed(self, path: str) -> bool:
        """Check if path is within allowed boundaries."""
        path_obj = Path(path).resolve()

        # Check blocked paths first
        for blocked in (self.config.blocked_paths or []):
            if path_obj.is_relative_to(Path(blocked).resolve()):
                return False

        # If no allowed paths specified, allow only temp dir
        if not self.config.allowed_paths:
            return bool(self._temp_dir and path_obj.is_relative_to(Path(self._temp_dir).resolve()))

        # Check against allowed paths
        return any(path_obj.is_relative_to(Path(allowed).resolve()) for allowed in self.config.allowed_paths)

    @contextmanager
    def isolate(self):
        """Context manager for isolated execution environment."""
        self._original_cwd = os.getcwd()
        self._temp_dir = tempfile.mkdtemp(prefix="astra_sandbox_")
        os.chdir(self._temp_dir)

        # Store original env vars we might modify
        original_env = {}
        if not self.config.allow_network:
            original_env["HTTP_PROXY"] = os.environ.get("HTTP_PROXY")
            original_env["HTTPS_PROXY"] = os.environ.get("HTTPS_PROXY")
            os.environ["HTTP_PROXY"] = ""
            os.environ["HTTPS_PROXY"] = ""
            os.environ["NO_PROXY"] = "*"

        try:
            yield self._temp_dir
        finally:
            os.chdir(self._original_cwd)
            # Restore env
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            # Cleanup temp dir
            if self._temp_dir and os.path.exists(self._temp_dir):
                shutil.rmtree(self._temp_dir, ignore_errors=True)

    def validate_file_access(self, path: str, write: bool = False) -> bool:
        """Validate if file access is permitted."""
        if not self._is_path_allowed(path):
            return False
        return not (write and not self.config.allow_filesystem_write)

    def validate_network_access(self, host: str, port: int) -> bool:
        """Validate if network access is permitted."""
        return self.config.allow_network
