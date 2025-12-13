"""Tests for agent filesystem tools."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import RunContext

from wunderunner.agents.tools import (
    SENSITIVE_PATTERNS,
    SKIP_EXTENSIONS,
    AgentDeps,
    _get_skip_dirs,
    _iter_files,
    _validate_path,
    check_files_exist,
    edit_file,
    file_stats,
    glob,
    grep,
    list_dir,
    read_file,
    register_tools,
    write_file,
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


class TestReadFile:
    """Test read_file tool."""

    @pytest.mark.asyncio
    async def test_reads_file_content(self, tmp_path):
        """read_file returns file content."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        deps = AgentDeps(project_dir=tmp_path)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            result = await read_file(ctx, "test.py")
            assert result == "print('hello')"

    @pytest.mark.asyncio
    async def test_truncates_large_files(self, tmp_path):
        """read_file truncates files exceeding max_file_size."""
        test_file = tmp_path / "large.txt"
        test_file.write_text("x" * 20000)

        deps = AgentDeps(project_dir=tmp_path, max_file_size=100)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            result = await read_file(ctx, "large.txt")
            assert "truncated" in result
            assert "20000 bytes" in result
            assert len(result) < 20000

    @pytest.mark.asyncio
    async def test_file_not_found_returns_error(self, tmp_path):
        """read_file returns error for missing files."""
        deps = AgentDeps(project_dir=tmp_path)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            result = await read_file(ctx, "nonexistent.py")
            assert "Error" in result
            assert "not found" in result

    @pytest.mark.asyncio
    async def test_path_escape_returns_error(self, tmp_path):
        """read_file returns error for path traversal."""
        deps = AgentDeps(project_dir=tmp_path)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            result = await read_file(ctx, "../etc/passwd")
            assert "Error" in result


class TestListDir:
    """Test list_dir tool."""

    @pytest.mark.asyncio
    async def test_lists_directory_contents(self, tmp_path):
        """list_dir returns directory contents."""
        (tmp_path / "src").mkdir()
        (tmp_path / "README.md").touch()
        (tmp_path / "app.py").touch()

        deps = AgentDeps(project_dir=tmp_path)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            result = await list_dir(ctx, ".")
            assert "src/" in result  # Directory suffixed with /
            assert "README.md" in result
            assert "app.py" in result

    @pytest.mark.asyncio
    async def test_directory_not_found_returns_error(self, tmp_path):
        """list_dir returns error for missing directory."""
        deps = AgentDeps(project_dir=tmp_path)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            result = await list_dir(ctx, "nonexistent")
            assert "Error" in result


class TestGlob:
    """Test glob tool."""

    @pytest.mark.asyncio
    async def test_finds_matching_files(self, tmp_path):
        """glob finds files matching pattern."""
        (tmp_path / "app.py").touch()
        (tmp_path / "test.py").touch()
        (tmp_path / "README.md").touch()

        deps = AgentDeps(project_dir=tmp_path)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            result = await glob(ctx, "*.py")
            assert "app.py" in result
            assert "test.py" in result
            assert "README.md" not in result

    @pytest.mark.asyncio
    async def test_no_matches_returns_message(self, tmp_path):
        """glob returns message when no matches."""
        deps = AgentDeps(project_dir=tmp_path)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            result = await glob(ctx, "*.nonexistent")
            assert "No files matching" in result


class TestGrep:
    """Test grep tool."""

    @pytest.mark.asyncio
    async def test_finds_pattern_in_files(self, tmp_path):
        """grep finds pattern in file contents."""
        test_file = tmp_path / "app.py"
        test_file.write_text("def hello():\n    print('world')\n")

        deps = AgentDeps(project_dir=tmp_path)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            result = await grep(ctx, "hello")
            assert "app.py" in result
            assert "def hello" in result

    @pytest.mark.asyncio
    async def test_invalid_regex_returns_error(self, tmp_path):
        """grep returns error for invalid regex."""
        deps = AgentDeps(project_dir=tmp_path)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            result = await grep(ctx, "[invalid")
            assert "Error" in result
            assert "Invalid regex" in result


class TestFileStats:
    """Test file_stats tool."""

    @pytest.mark.asyncio
    async def test_returns_file_metadata(self, tmp_path):
        """file_stats returns size and modification time."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        deps = AgentDeps(project_dir=tmp_path)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            result = await file_stats(ctx, "test.txt")
            assert "size:" in result
            assert "11 bytes" in result
            assert "modified:" in result


class TestWriteFile:
    """Test write_file tool."""

    @pytest.mark.asyncio
    async def test_writes_new_file(self, tmp_path):
        """write_file creates new file with content."""
        deps = AgentDeps(project_dir=tmp_path)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            result = await write_file(ctx, "new.txt", "hello world")
            assert "Successfully wrote" in result
            assert (tmp_path / "new.txt").read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_refuses_to_overwrite_sensitive_file(self, tmp_path):
        """write_file refuses to overwrite sensitive files."""
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET=original")

        deps = AgentDeps(project_dir=tmp_path)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            result = await write_file(ctx, ".env", "SECRET=hacked")
            assert "Error" in result
            assert "sensitive" in result.lower()
            # Original content preserved
            assert env_file.read_text() == "SECRET=original"


class TestEditFile:
    """Test edit_file tool."""

    @pytest.mark.asyncio
    async def test_replaces_string_in_file(self, tmp_path):
        """edit_file replaces old_string with new_string."""
        test_file = tmp_path / "app.py"
        test_file.write_text("def foo():\n    return 'bar'\n")

        deps = AgentDeps(project_dir=tmp_path)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            result = await edit_file(ctx, "app.py", "return 'bar'", "return 'baz'")
            assert "Successfully edited" in result
            assert "return 'baz'" in test_file.read_text()

    @pytest.mark.asyncio
    async def test_rejects_ambiguous_edit(self, tmp_path):
        """edit_file rejects when old_string appears multiple times."""
        test_file = tmp_path / "app.py"
        test_file.write_text("foo foo foo")

        deps = AgentDeps(project_dir=tmp_path)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            result = await edit_file(ctx, "app.py", "foo", "bar")
            assert "Error" in result
            assert "3 times" in result

    @pytest.mark.asyncio
    async def test_refuses_to_edit_sensitive_file(self, tmp_path):
        """edit_file refuses to edit sensitive files."""
        creds = tmp_path / "credentials.json"
        creds.write_text('{"key": "secret"}')

        deps = AgentDeps(project_dir=tmp_path)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            result = await edit_file(ctx, "credentials.json", "secret", "hacked")
            assert "Error" in result
            assert "sensitive" in result.lower()


class TestCheckFilesExist:
    """Test check_files_exist tool."""

    @pytest.mark.asyncio
    async def test_checks_multiple_paths(self, tmp_path):
        """check_files_exist checks multiple paths at once."""
        (tmp_path / "exists.txt").touch()

        deps = AgentDeps(project_dir=tmp_path)
        ctx = MagicMock(spec=RunContext)
        ctx.deps = deps

        with patch("wunderunner.agents.tools.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            result = await check_files_exist(ctx, ["exists.txt", "missing.txt"])
            assert "exists.txt: exists" in result
            assert "missing.txt: not found" in result


class TestRegisterTools:
    """Test register_tools function."""

    def test_registers_read_only_tools(self, tmp_path):
        """register_tools registers read-only tools by default."""
        from pydantic_ai import Agent

        agent = Agent(model="test", output_type=str, defer_model_check=True)

        # Mock the agent.tool method to track what was registered
        with patch.object(agent, 'tool') as mock_tool:
            register_tools(agent, include_write=False)

            # Verify read-only tools were registered
            assert mock_tool.call_count == 6  # read_file, list_dir, glob, grep, file_stats, check_files_exist

            # Verify the actual functions that were registered
            registered_funcs = [call[0][0] for call in mock_tool.call_args_list]
            registered_names = {func.__name__ for func in registered_funcs}

            assert "read_file" in registered_names
            assert "list_dir" in registered_names
            assert "glob" in registered_names
            assert "grep" in registered_names
            assert "file_stats" in registered_names
            assert "check_files_exist" in registered_names
            assert "write_file" not in registered_names
            assert "edit_file" not in registered_names

    def test_registers_write_tools_when_enabled(self, tmp_path):
        """register_tools includes write tools when include_write=True."""
        from pydantic_ai import Agent

        agent = Agent(model="test", output_type=str, defer_model_check=True)

        # Mock the agent.tool method to track what was registered
        with patch.object(agent, 'tool') as mock_tool:
            register_tools(agent, include_write=True)

            # Verify all tools were registered (6 read-only + 2 write tools)
            assert mock_tool.call_count == 8

            # Verify the actual functions that were registered
            registered_funcs = [call[0][0] for call in mock_tool.call_args_list]
            registered_names = {func.__name__ for func in registered_funcs}

            assert "write_file" in registered_names
            assert "edit_file" in registered_names
