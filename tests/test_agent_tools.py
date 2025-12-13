"""Tests for agent filesystem tools."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from wunderunner.agents.tools import (
    SENSITIVE_PATTERNS,
    SKIP_EXTENSIONS,
    AgentDeps,
    _get_skip_dirs,
    _iter_files,
    _validate_path,
)


class TestAgentDeps:
    """Test AgentDeps dataclass."""

    def test_minimal_deps(self, tmp_path):
        """AgentDeps with just project_dir."""
        deps = AgentDeps(project_dir=tmp_path)
        assert deps.project_dir == tmp_path
        assert deps.max_file_size == 15_000

    def test_custom_max_file_size(self, tmp_path):
        """AgentDeps with custom max_file_size."""
        deps = AgentDeps(project_dir=tmp_path, max_file_size=5000)
        assert deps.max_file_size == 5000


class TestGetSkipDirs:
    """Test _get_skip_dirs function."""

    def test_returns_frozenset(self):
        """_get_skip_dirs returns a frozenset."""
        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            skip_dirs = _get_skip_dirs()
            assert isinstance(skip_dirs, frozenset)

    def test_includes_standard_dirs(self):
        """_get_skip_dirs includes standard skip directories."""
        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            skip_dirs = _get_skip_dirs()
            assert ".git" in skip_dirs
            assert "node_modules" in skip_dirs
            assert ".venv" in skip_dirs
            assert "__pycache__" in skip_dirs

    def test_includes_cache_dir_from_settings(self):
        """_get_skip_dirs includes cache_dir from settings."""
        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".custom_cache"
            skip_dirs = _get_skip_dirs()
            assert ".custom_cache" in skip_dirs


class TestSkipExtensions:
    """Test SKIP_EXTENSIONS constant."""

    def test_includes_binary_extensions(self):
        """SKIP_EXTENSIONS includes common binary types."""
        assert ".pyc" in SKIP_EXTENSIONS
        assert ".so" in SKIP_EXTENSIONS
        assert ".dll" in SKIP_EXTENSIONS
        assert ".exe" in SKIP_EXTENSIONS

    def test_includes_lock_files(self):
        """SKIP_EXTENSIONS includes lock files."""
        assert ".lock" in SKIP_EXTENSIONS

    def test_includes_media_files(self):
        """SKIP_EXTENSIONS includes media files."""
        assert ".png" in SKIP_EXTENSIONS
        assert ".jpg" in SKIP_EXTENSIONS
        assert ".pdf" in SKIP_EXTENSIONS


class TestSensitivePatterns:
    """Test SENSITIVE_PATTERNS constant."""

    def test_includes_env_files(self):
        """SENSITIVE_PATTERNS includes .env files."""
        assert ".env" in SENSITIVE_PATTERNS

    def test_includes_credentials(self):
        """SENSITIVE_PATTERNS includes credential patterns."""
        assert "credentials" in SENSITIVE_PATTERNS
        assert "secret" in SENSITIVE_PATTERNS
        assert ".key" in SENSITIVE_PATTERNS
        assert ".pem" in SENSITIVE_PATTERNS


class TestValidatePath:
    """Test _validate_path security function."""

    def test_valid_path_within_project(self, tmp_path):
        """Valid relative path resolves correctly."""
        deps = AgentDeps(project_dir=tmp_path)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").touch()

        result = _validate_path(deps, "src/app.py")
        assert result == tmp_path / "src" / "app.py"

    def test_path_traversal_blocked(self, tmp_path):
        """Path traversal attempts are blocked."""
        deps = AgentDeps(project_dir=tmp_path)

        with pytest.raises(ValueError, match="escapes project"):
            _validate_path(deps, "../etc/passwd")

        with pytest.raises(ValueError, match="escapes project"):
            _validate_path(deps, "foo/../../etc/passwd")

    def test_absolute_path_outside_project_blocked(self, tmp_path):
        """Absolute paths outside project are blocked."""
        deps = AgentDeps(project_dir=tmp_path)

        with pytest.raises(ValueError, match="escapes project"):
            _validate_path(deps, "/etc/passwd")

    def test_cache_dir_access_blocked(self, tmp_path):
        """Access to cache directory is blocked."""
        deps = AgentDeps(project_dir=tmp_path)

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"

            with pytest.raises(ValueError, match="Cannot access .wunderunner"):
                _validate_path(deps, ".wunderunner/context.json")

    def test_nested_cache_access_blocked(self, tmp_path):
        """Nested paths starting with cache dir are blocked."""
        deps = AgentDeps(project_dir=tmp_path)

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"

            with pytest.raises(ValueError, match="Cannot access"):
                _validate_path(deps, ".wunderunner/nested/file.txt")

    def test_current_dir_path(self, tmp_path):
        """Current directory path works."""
        deps = AgentDeps(project_dir=tmp_path)
        result = _validate_path(deps, ".")
        assert result == tmp_path


class TestIterFiles:
    """Test _iter_files function."""

    def test_lists_files_recursively(self, tmp_path):
        """_iter_files lists files in nested directories."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").touch()
        (tmp_path / "src" / "lib").mkdir()
        (tmp_path / "src" / "lib" / "utils.py").touch()
        (tmp_path / "README.md").touch()

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            files = _iter_files(tmp_path)
            filenames = {f.name for f in files}

            assert "app.py" in filenames
            assert "utils.py" in filenames
            assert "README.md" in filenames

    def test_skips_skip_dirs(self, tmp_path):
        """_iter_files skips configured directories."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").touch()
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "lodash.js").touch()

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            files = _iter_files(tmp_path)
            filenames = {f.name for f in files}

            assert "app.py" in filenames
            assert "lodash.js" not in filenames

    def test_skips_binary_extensions(self, tmp_path):
        """_iter_files skips binary file extensions."""
        (tmp_path / "app.py").touch()
        (tmp_path / "app.pyc").touch()
        (tmp_path / "lib.so").touch()
        (tmp_path / "image.png").touch()

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            files = _iter_files(tmp_path)
            filenames = {f.name for f in files}

            assert "app.py" in filenames
            assert "app.pyc" not in filenames
            assert "lib.so" not in filenames
            assert "image.png" not in filenames

    def test_respects_max_files_limit(self, tmp_path):
        """_iter_files respects max_files parameter."""
        for i in range(20):
            (tmp_path / f"file{i}.py").touch()

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            files = _iter_files(tmp_path, max_files=5)
            assert len(files) == 5
