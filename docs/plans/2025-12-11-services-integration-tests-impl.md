# Services Integration Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add integration tests for `activities/services.py` with mocked Docker and HTTP clients.

**Architecture:** Tests use `unittest.mock` to patch Docker client and httpx. Each test class focuses on one public function. Fixtures provide reusable mock configurations.

**Tech Stack:** pytest, pytest-asyncio, unittest.mock

---

## Task 1: Create Test File with Fixtures

**Files:**
- Create: `tests/test_services.py`

**Step 1: Create test file with imports and fixtures**

```python
"""Integration tests for services activities."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from wunderunner.activities import services
from wunderunner.exceptions import HealthcheckError, ServicesError, StartError


@pytest.fixture
def mock_container():
    """Create a mock container with configurable state."""
    def _make_container(
        container_id: str = "abc123",
        status: str = "running",
        name: str = "test-container",
        ports: dict | None = None,
        logs: bytes = b"container logs here",
    ):
        container = MagicMock()
        container.id = container_id
        container.status = status
        container.name = name
        container.logs.return_value = logs
        container.attrs = {
            "NetworkSettings": {
                "Ports": ports or {}
            }
        }
        return container
    return _make_container


@pytest.fixture
def mock_docker_client(mock_container):
    """Create a mock Docker client."""
    client = MagicMock()
    container = mock_container()
    client.containers.get.return_value = container
    return client
```

**Step 2: Run to verify imports work**

Run: `uv run pytest tests/test_services.py --collect-only`
Expected: "no tests ran" (collection succeeds, no tests yet)

**Step 3: Commit**

```bash
git add tests/test_services.py
git commit -m "test: add test_services.py with mock fixtures"
```

---

## Task 2: Test healthcheck - Empty Container List

**Files:**
- Modify: `tests/test_services.py`

**Step 1: Write the failing test**

Add to `tests/test_services.py`:

```python
class TestHealthcheck:
    """Tests for healthcheck function."""

    @pytest.mark.asyncio
    async def test_empty_container_list_raises_error(self):
        """Healthcheck with no containers should raise HealthcheckError."""
        with pytest.raises(HealthcheckError, match="No containers to check"):
            await services.healthcheck([])
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_services.py::TestHealthcheck::test_empty_container_list_raises_error -v`
Expected: PASS (this tests existing behavior)

**Step 3: Commit**

```bash
git add tests/test_services.py
git commit -m "test: healthcheck raises error for empty container list"
```

---

## Task 3: Test healthcheck - Happy Path

**Files:**
- Modify: `tests/test_services.py`

**Step 1: Write the failing test**

Add to `TestHealthcheck` class:

```python
    @pytest.mark.asyncio
    async def test_happy_path_containers_running_http_success(self, mock_container):
        """Healthcheck passes when containers run and HTTP returns 200."""
        container = mock_container(
            status="running",
            ports={"8000/tcp": [{"HostPort": "8000"}]},
        )
        mock_client = MagicMock()
        mock_client.containers.get.return_value = container

        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch("wunderunner.activities.services.get_client", return_value=mock_client),
            patch("httpx.AsyncClient") as mock_httpx,
        ):
            mock_httpx_instance = AsyncMock()
            mock_httpx_instance.get.return_value = mock_response
            mock_httpx.return_value.__aenter__.return_value = mock_httpx_instance

            # Should complete without raising
            await services.healthcheck(["abc123"], timeout=5)
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_services.py::TestHealthcheck::test_happy_path_containers_running_http_success -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_services.py
git commit -m "test: healthcheck happy path with running containers and HTTP 200"
```

---

## Task 4: Test healthcheck - Container Exits

**Files:**
- Modify: `tests/test_services.py`

**Step 1: Write the failing test**

Add to `TestHealthcheck` class:

```python
    @pytest.mark.asyncio
    async def test_container_exits_raises_error(self, mock_container):
        """Healthcheck fails when container exits."""
        container = mock_container(
            status="exited",
            logs=b"Error: process crashed",
        )
        mock_client = MagicMock()
        mock_client.containers.get.return_value = container

        with patch("wunderunner.activities.services.get_client", return_value=mock_client):
            with pytest.raises(HealthcheckError, match="exited"):
                await services.healthcheck(["abc123"], timeout=5)
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_services.py::TestHealthcheck::test_container_exits_raises_error -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_services.py
git commit -m "test: healthcheck fails when container exits"
```

---

## Task 5: Test healthcheck - Timeout Waiting for Containers

**Files:**
- Modify: `tests/test_services.py`

**Step 1: Write the failing test**

Add to `TestHealthcheck` class:

```python
    @pytest.mark.asyncio
    async def test_timeout_waiting_for_containers(self, mock_container):
        """Healthcheck times out if containers never reach running state."""
        container = mock_container(status="created")  # Never becomes running
        mock_client = MagicMock()
        mock_client.containers.get.return_value = container

        with (
            patch("wunderunner.activities.services.get_client", return_value=mock_client),
            patch("wunderunner.activities.services.asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(HealthcheckError, match="timed out.*waiting for containers"):
                await services.healthcheck(["abc123"], timeout=1)
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_services.py::TestHealthcheck::test_timeout_waiting_for_containers -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_services.py
git commit -m "test: healthcheck times out waiting for containers"
```

---

## Task 6: Test healthcheck - Timeout Waiting for HTTP

**Files:**
- Modify: `tests/test_services.py`

**Step 1: Write the failing test**

Add to `TestHealthcheck` class:

```python
    @pytest.mark.asyncio
    async def test_timeout_waiting_for_http(self, mock_container):
        """Healthcheck times out if HTTP never responds."""
        container = mock_container(
            status="running",
            ports={"8000/tcp": [{"HostPort": "8000"}]},
        )
        mock_client = MagicMock()
        mock_client.containers.get.return_value = container

        with (
            patch("wunderunner.activities.services.get_client", return_value=mock_client),
            patch("httpx.AsyncClient") as mock_httpx,
            patch("wunderunner.activities.services.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_httpx_instance = AsyncMock()
            mock_httpx_instance.get.side_effect = httpx.RequestError("Connection refused")
            mock_httpx.return_value.__aenter__.return_value = mock_httpx_instance

            with pytest.raises(HealthcheckError, match="timed out.*HTTP"):
                await services.healthcheck(["abc123"], timeout=1)
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_services.py::TestHealthcheck::test_timeout_waiting_for_http -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_services.py
git commit -m "test: healthcheck times out waiting for HTTP"
```

---

## Task 7: Test healthcheck - HTTP 500 Error

**Files:**
- Modify: `tests/test_services.py`

**Step 1: Write the failing test**

Add to `TestHealthcheck` class:

```python
    @pytest.mark.asyncio
    async def test_http_500_error_fails_immediately(self, mock_container):
        """Healthcheck fails immediately on HTTP 500."""
        container = mock_container(
            status="running",
            ports={"8000/tcp": [{"HostPort": "8000"}]},
        )
        mock_client = MagicMock()
        mock_client.containers.get.return_value = container

        mock_response = MagicMock()
        mock_response.status_code = 500

        with (
            patch("wunderunner.activities.services.get_client", return_value=mock_client),
            patch("httpx.AsyncClient") as mock_httpx,
        ):
            mock_httpx_instance = AsyncMock()
            mock_httpx_instance.get.return_value = mock_response
            mock_httpx.return_value.__aenter__.return_value = mock_httpx_instance

            with pytest.raises(HealthcheckError, match="HTTP 500"):
                await services.healthcheck(["abc123"], timeout=5)
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_services.py::TestHealthcheck::test_http_500_error_fails_immediately -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_services.py
git commit -m "test: healthcheck fails immediately on HTTP 500"
```

---

## Task 8: Test healthcheck - No HTTP Ports

**Files:**
- Modify: `tests/test_services.py`

**Step 1: Write the failing test**

Add to `TestHealthcheck` class:

```python
    @pytest.mark.asyncio
    async def test_no_http_ports_succeeds(self, mock_container):
        """Healthcheck passes when no ports exposed (skips HTTP phase)."""
        container = mock_container(status="running", ports={})
        mock_client = MagicMock()
        mock_client.containers.get.return_value = container

        with patch("wunderunner.activities.services.get_client", return_value=mock_client):
            # Should complete without raising
            await services.healthcheck(["abc123"], timeout=5)
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_services.py::TestHealthcheck::test_no_http_ports_succeeds -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_services.py
git commit -m "test: healthcheck succeeds when no HTTP ports exposed"
```

---

## Task 9: Test healthcheck - Connection Refused Then Success

**Files:**
- Modify: `tests/test_services.py`

**Step 1: Write the failing test**

Add to `TestHealthcheck` class:

```python
    @pytest.mark.asyncio
    async def test_connection_refused_then_success(self, mock_container):
        """Healthcheck retries and succeeds after initial connection refused."""
        container = mock_container(
            status="running",
            ports={"8000/tcp": [{"HostPort": "8000"}]},
        )
        mock_client = MagicMock()
        mock_client.containers.get.return_value = container

        mock_response = MagicMock()
        mock_response.status_code = 200

        call_count = 0

        async def get_with_retry(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.RequestError("Connection refused")
            return mock_response

        with (
            patch("wunderunner.activities.services.get_client", return_value=mock_client),
            patch("httpx.AsyncClient") as mock_httpx,
            patch("wunderunner.activities.services.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_httpx_instance = AsyncMock()
            mock_httpx_instance.get.side_effect = get_with_retry
            mock_httpx.return_value.__aenter__.return_value = mock_httpx_instance

            await services.healthcheck(["abc123"], timeout=10)
            assert call_count >= 3
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_services.py::TestHealthcheck::test_connection_refused_then_success -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_services.py
git commit -m "test: healthcheck retries on connection refused"
```

---

## Task 10: Test start - Compose File Missing

**Files:**
- Modify: `tests/test_services.py`

**Step 1: Write the failing test**

Add new class to `tests/test_services.py`:

```python
class TestStart:
    """Tests for start function."""

    @pytest.mark.asyncio
    async def test_compose_file_missing_raises_error(self, tmp_path):
        """Start raises error when docker-compose.yaml doesn't exist."""
        with pytest.raises(StartError, match="docker-compose.yaml not found"):
            await services.start(tmp_path)
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_services.py::TestStart::test_compose_file_missing_raises_error -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_services.py
git commit -m "test: start raises error when compose file missing"
```

---

## Task 11: Test start - Happy Path

**Files:**
- Modify: `tests/test_services.py`

**Step 1: Write the failing test**

Add to `TestStart` class:

```python
    @pytest.mark.asyncio
    async def test_happy_path_returns_container_ids(self, tmp_path):
        """Start returns container IDs on success."""
        compose_file = tmp_path / "docker-compose.yaml"
        compose_file.write_text("version: '3'\nservices:\n  app:\n    image: alpine\n")

        async def mock_subprocess(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"", b""))
            return proc

        async def mock_subprocess_ps(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            # docker compose ps -q returns container IDs
            proc.communicate = AsyncMock(return_value=(b"container1\ncontainer2\n", b""))
            return proc

        call_count = 0

        async def create_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # First two calls are down and up, third is ps
            if call_count <= 2:
                return await mock_subprocess(*args, **kwargs)
            return await mock_subprocess_ps(*args, **kwargs)

        with patch("asyncio.create_subprocess_exec", side_effect=create_subprocess):
            result = await services.start(tmp_path)
            assert result == ["container1", "container2"]
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_services.py::TestStart::test_happy_path_returns_container_ids -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_services.py
git commit -m "test: start returns container IDs on success"
```

---

## Task 12: Test start - Compose Up Fails

**Files:**
- Modify: `tests/test_services.py`

**Step 1: Write the failing test**

Add to `TestStart` class:

```python
    @pytest.mark.asyncio
    async def test_compose_up_fails_raises_error(self, tmp_path):
        """Start raises error when docker compose up fails."""
        compose_file = tmp_path / "docker-compose.yaml"
        compose_file.write_text("version: '3'\nservices:\n  app:\n    image: alpine\n")

        call_count = 0

        async def create_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            proc = MagicMock()
            if call_count == 1:
                # down succeeds
                proc.returncode = 0
                proc.communicate = AsyncMock(return_value=(b"", b""))
            else:
                # up fails
                proc.returncode = 1
                proc.communicate = AsyncMock(return_value=(b"Error: build failed", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=create_subprocess):
            with pytest.raises(StartError, match="docker compose up failed"):
                await services.start(tmp_path)
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_services.py::TestStart::test_compose_up_fails_raises_error -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_services.py
git commit -m "test: start raises error when compose up fails"
```

---

## Task 13: Test start - No Containers Started

**Files:**
- Modify: `tests/test_services.py`

**Step 1: Write the failing test**

Add to `TestStart` class:

```python
    @pytest.mark.asyncio
    async def test_no_containers_started_raises_error(self, tmp_path):
        """Start raises error when no containers are started."""
        compose_file = tmp_path / "docker-compose.yaml"
        compose_file.write_text("version: '3'\nservices:\n  app:\n    image: alpine\n")

        async def create_subprocess(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            # ps returns empty (no containers)
            proc.communicate = AsyncMock(return_value=(b"", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=create_subprocess):
            with pytest.raises(StartError, match="No containers started"):
                await services.start(tmp_path)
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_services.py::TestStart::test_no_containers_started_raises_error -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_services.py
git commit -m "test: start raises error when no containers started"
```

---

## Task 14: Test stop - Happy Path and No Compose File

**Files:**
- Modify: `tests/test_services.py`

**Step 1: Write the failing tests**

Add new class to `tests/test_services.py`:

```python
class TestStop:
    """Tests for stop function."""

    @pytest.mark.asyncio
    async def test_happy_path_runs_compose_down(self, tmp_path):
        """Stop runs docker compose down when file exists."""
        compose_file = tmp_path / "docker-compose.yaml"
        compose_file.write_text("version: '3'\nservices:\n  app:\n    image: alpine\n")

        async def create_subprocess(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=create_subprocess) as mock_exec:
            await services.stop(tmp_path)
            mock_exec.assert_called_once()
            # Verify docker compose down was called
            call_args = mock_exec.call_args[0]
            assert "docker" in call_args
            assert "down" in call_args

    @pytest.mark.asyncio
    async def test_no_compose_file_returns_early(self, tmp_path):
        """Stop returns early when no compose file exists."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            await services.stop(tmp_path)
            mock_exec.assert_not_called()
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_services.py::TestStop -v`
Expected: PASS (2 tests)

**Step 3: Commit**

```bash
git add tests/test_services.py
git commit -m "test: stop runs compose down or returns early"
```

---

## Task 15: Test generate - Happy Path

**Files:**
- Modify: `tests/test_services.py`

**Step 1: Write the failing test**

Add new class to `tests/test_services.py`:

```python
class TestGenerate:
    """Tests for generate function."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_compose_yaml(self):
        """Generate returns compose YAML from agent."""
        from wunderunner.models.analysis import Analysis, BuildStrategy, ProjectStructure

        # Minimal analysis object
        analysis = Analysis(
            project_structure=ProjectStructure(
                runtime="python",
                framework=None,
                package_manager="pip",
                entry_point="app.py",
            ),
            build_strategy=BuildStrategy(
                base_image="python:3.11-slim",
                install_command="pip install -r requirements.txt",
                build_command=None,
                start_command="python app.py",
            ),
            env_vars=[],
        )

        mock_result = MagicMock()
        mock_result.output.compose_yaml = "version: '3'\nservices:\n  app:\n    build: .\n"

        with patch("wunderunner.activities.services.compose_agent") as mock_agent:
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)

            with patch("wunderunner.activities.services.get_fallback_model"):
                result = await services.generate(
                    analysis=analysis,
                    dockerfile_content="FROM python:3.11\n",
                    learnings=[],
                    hints=[],
                )

                assert "version" in result
                assert "services" in result
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_services.py::TestGenerate::test_happy_path_returns_compose_yaml -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_services.py
git commit -m "test: generate returns compose YAML from agent"
```

---

## Task 16: Test generate - AI Error

**Files:**
- Modify: `tests/test_services.py`

**Step 1: Write the failing test**

Add to `TestGenerate` class:

```python
    @pytest.mark.asyncio
    async def test_ai_error_raises_services_error(self):
        """Generate raises ServicesError when agent fails."""
        from wunderunner.models.analysis import Analysis, BuildStrategy, ProjectStructure

        analysis = Analysis(
            project_structure=ProjectStructure(
                runtime="python",
                framework=None,
                package_manager="pip",
                entry_point="app.py",
            ),
            build_strategy=BuildStrategy(
                base_image="python:3.11-slim",
                install_command="pip install -r requirements.txt",
                build_command=None,
                start_command="python app.py",
            ),
            env_vars=[],
        )

        with patch("wunderunner.activities.services.compose_agent") as mock_agent:
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(side_effect=Exception("API error"))

            with patch("wunderunner.activities.services.get_fallback_model"):
                with pytest.raises(ServicesError, match="Failed to generate"):
                    await services.generate(
                        analysis=analysis,
                        dockerfile_content="FROM python:3.11\n",
                        learnings=[],
                        hints=[],
                    )
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_services.py::TestGenerate::test_ai_error_raises_services_error -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_services.py
git commit -m "test: generate raises ServicesError on agent failure"
```

---

## Task 17: Run Full Test Suite and Final Commit

**Files:**
- None (verification only)

**Step 1: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 2: Run linter**

Run: `make lint`
Expected: All checks passed

**Step 3: Final commit if any cleanup needed**

```bash
git status
# If clean, skip commit
# If changes, commit with appropriate message
```

---

## Summary

17 tasks total:
- 1 setup task (fixtures)
- 8 healthcheck tests
- 4 start tests
- 2 stop tests
- 2 generate tests
- 1 verification task

Estimated: ~30-45 minutes to implement
