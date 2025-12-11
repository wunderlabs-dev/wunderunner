"""Tests for services activity."""

import inspect


def test_generate_accepts_services_param():
    """services.generate accepts services parameter."""
    from wunderunner.activities import services

    sig = inspect.signature(services.generate)
    params = list(sig.parameters.keys())
    assert "services" in params
