"""Tests for OAuth callback server."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from wunderunner.auth.server import CallbackServer, get_success_page


class TestGetSuccessPage:
    """Test success page loading."""

    def test_returns_html(self):
        """get_success_page returns HTML content."""
        html = get_success_page()
        assert "<html" in html.lower()
        assert "</html>" in html.lower()

    def test_includes_success_message(self):
        """Success page includes authentication success message."""
        html = get_success_page()
        assert "authenticated" in html.lower() or "success" in html.lower()


class TestCallbackServer:
    """Test CallbackServer class."""

    @pytest.mark.asyncio
    async def test_server_binds_to_localhost(self):
        """Server binds to localhost."""
        server = CallbackServer(port=0)  # Random available port
        await server.start()
        try:
            assert server.host == "127.0.0.1"
            assert server.port > 0
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_callback_url_format(self):
        """callback_url returns correct format."""
        server = CallbackServer(port=0)
        await server.start()
        try:
            url = server.callback_url
            assert url.startswith("http://127.0.0.1:")
            assert "/callback" in url
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_wait_for_callback_returns_code(self):
        """wait_for_callback returns authorization code."""
        server = CallbackServer(port=0)
        await server.start()

        async def simulate_callback():
            await asyncio.sleep(0.1)
            # Simulate browser callback
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = f"{server.callback_url}?code=test_auth_code&state=test_state"
                async with session.get(url) as resp:
                    assert resp.status == 200

        try:
            callback_task = asyncio.create_task(simulate_callback())
            code = await asyncio.wait_for(
                server.wait_for_callback(expected_state="test_state"),
                timeout=5.0,
            )
            await callback_task
            assert code == "test_auth_code"
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_wait_for_callback_validates_state(self):
        """wait_for_callback raises on state mismatch."""
        server = CallbackServer(port=0)
        await server.start()

        async def simulate_callback():
            await asyncio.sleep(0.1)
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = f"{server.callback_url}?code=test_code&state=wrong_state"
                async with session.get(url) as resp:
                    pass  # Server returns error page

        try:
            callback_task = asyncio.create_task(simulate_callback())
            with pytest.raises(Exception):  # OAuthCallbackError or timeout
                await asyncio.wait_for(
                    server.wait_for_callback(expected_state="correct_state"),
                    timeout=2.0,
                )
            await callback_task
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_wait_for_callback_timeout(self):
        """wait_for_callback raises on timeout."""
        server = CallbackServer(port=0)
        await server.start()

        try:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(
                    server.wait_for_callback(expected_state="test"),
                    timeout=0.1,
                )
        finally:
            await server.stop()
