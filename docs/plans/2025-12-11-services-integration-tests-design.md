# Integration Tests for services.py

## Overview

Add integration tests for `activities/services.py` with mocked Docker and HTTP clients. Tests verify orchestration logic without requiring Docker or making real API calls.

## Approach

- Mock Docker via patching `wunderunner.activities.docker.get_client`
- Mock HTTP via patching `httpx.AsyncClient`
- Mock AI via patching the compose agent
- Use short timeouts (1-2s) and mock `asyncio.sleep` for speed

## File Structure

```
tests/
  test_services.py      # New integration tests
  conftest.py           # Shared fixtures (if needed)
```

## Fixtures

### `mock_docker_client`

Returns a mock `docker.DockerClient` with configurable:
- `containers.get()` - returns mock container with `.status`, `.logs()`, `.name`, `.attrs`
- Container status progression (created → running → exited)

### `mock_httpx_client`

Returns a mock `httpx.AsyncClient` with configurable:
- Response status codes
- `RequestError` for connection refused
- Response sequences (fail then succeed)

## Test Cases

### TestHealthcheck

| Test | Setup | Expected |
|------|-------|----------|
| `test_happy_path` | Containers running, HTTP 200 | Success |
| `test_container_exits` | One container status="exited" | `HealthcheckError` with logs |
| `test_timeout_waiting_for_containers` | Containers stay "created" | Timeout error |
| `test_timeout_waiting_for_http` | Running but HTTP never responds | Timeout error |
| `test_http_500_error` | HTTP returns 500 | Immediate `HealthcheckError` |
| `test_no_http_ports` | No exposed ports | Success (skips HTTP phase) |
| `test_connection_refused_then_success` | HTTP fails twice, then 200 | Success |

### TestStart

| Test | Setup | Expected |
|------|-------|----------|
| `test_happy_path` | Compose succeeds, returns IDs | List of container IDs |
| `test_compose_file_missing` | No docker-compose.yaml | `StartError` |
| `test_compose_up_fails` | Exit code 1 | `StartError` with output |
| `test_no_containers_started` | Compose succeeds, empty ps | `StartError` |

### TestStop

| Test | Setup | Expected |
|------|-------|----------|
| `test_happy_path` | Compose file exists | Runs `docker compose down` |
| `test_no_compose_file` | No file | Returns without error |

### TestGenerate

| Test | Setup | Expected |
|------|-------|----------|
| `test_happy_path` | Mocked agent returns YAML | Returns compose content |
| `test_ai_error` | Agent raises exception | `ServicesError` |
| `test_with_existing_compose` | Pass existing content | Agent receives it for refinement |

## Implementation Notes

- Patch at the module level where functions are imported, not where defined
- Use `pytest.mark.asyncio` for all async tests
- Mock `asyncio.sleep` to avoid real delays in timeout tests
- Container mock needs `.attrs["NetworkSettings"]["Ports"]` for port detection
