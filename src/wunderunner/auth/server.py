"""OAuth callback server for handling browser redirects."""

import asyncio
import logging
from importlib.resources import files
from urllib.parse import parse_qs, urlparse

from aiohttp import web

from wunderunner.exceptions import OAuthCallbackError

logger = logging.getLogger(__name__)


def get_success_page() -> str:
    """Load the success HTML page."""
    return files("wunderunner.auth.pages").joinpath("success.html").read_text()


def _get_error_page(message: str) -> str:
    """Generate error HTML page."""
    return f"""<!DOCTYPE html>
<html>
<head><title>Authentication Error</title></head>
<body style="background:#0d1117;color:#f85149;font-family:monospace;padding:2rem;">
<h1>Authentication Error</h1>
<p>{message}</p>
</body>
</html>"""


class CallbackServer:
    """Temporary HTTP server to receive OAuth callbacks."""

    def __init__(self, port: int = 0):
        """Initialize callback server.

        Args:
            port: Port to bind to. 0 = random available port.
        """
        self.host = "127.0.0.1"
        self._requested_port = port
        self.port = 0
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._code_future: asyncio.Future[str] | None = None
        self._expected_state: str | None = None

    @property
    def callback_url(self) -> str:
        """Get the callback URL for this server."""
        return f"http://{self.host}:{self.port}/callback"

    async def start(self) -> None:
        """Start the callback server."""
        self._app = web.Application()
        self._app.router.add_get("/callback", self._handle_callback)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        self._site = web.TCPSite(self._runner, self.host, self._requested_port)
        await self._site.start()

        # Get actual port if we requested 0
        assert self._site._server is not None
        sockets = self._site._server.sockets
        if sockets:
            self.port = sockets[0].getsockname()[1]

        logger.debug("Callback server started on %s:%d", self.host, self.port)

    async def stop(self) -> None:
        """Stop the callback server."""
        if self._runner:
            await self._runner.cleanup()
        self._app = None
        self._runner = None
        self._site = None

    async def wait_for_callback(self, expected_state: str) -> str:
        """Wait for OAuth callback and return authorization code.

        Args:
            expected_state: Expected state parameter for CSRF validation.

        Returns:
            Authorization code from callback.

        Raises:
            OAuthCallbackError: If state doesn't match or callback fails.
        """
        self._expected_state = expected_state
        self._code_future = asyncio.get_event_loop().create_future()

        try:
            return await self._code_future
        finally:
            self._code_future = None
            self._expected_state = None

    async def _handle_callback(self, request: web.Request) -> web.Response:
        """Handle OAuth callback request."""
        query = parse_qs(request.query_string)

        # Check for error response
        if "error" in query:
            error = query.get("error", ["unknown"])[0]
            description = query.get("error_description", [""])[0]
            message = f"OAuth error: {error} - {description}"
            logger.error(message)
            if self._code_future and not self._code_future.done():
                self._code_future.set_exception(OAuthCallbackError(message))
            return web.Response(
                text=_get_error_page(message),
                content_type="text/html",
            )

        # Validate state
        state = query.get("state", [None])[0]
        if state != self._expected_state:
            message = "State mismatch - possible CSRF attack"
            logger.error(message)
            if self._code_future and not self._code_future.done():
                self._code_future.set_exception(OAuthCallbackError(message))
            return web.Response(
                text=_get_error_page(message),
                content_type="text/html",
            )

        # Extract code
        code = query.get("code", [None])[0]
        if not code:
            message = "No authorization code in callback"
            logger.error(message)
            if self._code_future and not self._code_future.done():
                self._code_future.set_exception(OAuthCallbackError(message))
            return web.Response(
                text=_get_error_page(message),
                content_type="text/html",
            )

        # Success
        logger.debug("Received authorization code")
        if self._code_future and not self._code_future.done():
            self._code_future.set_result(code)

        return web.Response(
            text=get_success_page(),
            content_type="text/html",
        )
