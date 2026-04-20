"""Tests for app lifespan and server entry point."""

from unittest.mock import AsyncMock, patch

from mcp_docs.app import AppContext, app_lifespan
from mcp_docs.client import DocsClient
from mcp_docs.config import DocsConfig


class TestLifespan:
    async def test_lifespan_creates_and_closes_client(self) -> None:
        mock_config = DocsConfig(base_url="https://test.local", auth_mode="session", session_cookie="x")
        mock_client = AsyncMock(spec=DocsClient)
        with (
            patch("mcp_docs.app.DocsConfig", return_value=mock_config),
            patch("mcp_docs.app.DocsClient", return_value=mock_client),
        ):
            async with app_lifespan(None) as ctx:  # type: ignore[arg-type]
                assert isinstance(ctx, AppContext)
                assert ctx.client is mock_client
                assert ctx.config is mock_config
        mock_client.close.assert_awaited_once()


class TestServer:
    def test_main_calls_mcp_run(self) -> None:
        with (
            patch("mcp_docs.app.mcp") as mock_mcp,
            patch("sys.argv", ["mcp-docs"]),
        ):
            from mcp_docs.server import main

            main()
            mock_mcp.run.assert_called_once()
