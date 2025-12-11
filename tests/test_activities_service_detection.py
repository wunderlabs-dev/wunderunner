"""Tests for service detection activity."""


def test_detect_services_function_exists():
    """detect_services function exists and is importable."""
    from wunderunner.activities.service_detection import detect_services

    assert callable(detect_services)


def test_confirm_services_function_exists():
    """confirm_services function exists."""
    from wunderunner.activities.service_detection import confirm_services

    assert callable(confirm_services)
