"""Tests for app lifespan and server entry point."""

from unittest.mock import AsyncMock, patch

from mcp_docs.app import AppContext, app_lifespan
from mcp_docs.client import DocsClient


class TestLifespan:
    async def test_lifespan_creates_and_closes_client(self) -> None:
        mock_client = AsyncMock(spec=DocsClient)
        with patch("mcp_docs.app.create_client_from_env", return_value=mock_client):
            async with app_lifespan(None) as ctx:  # type: ignore[arg-type]
                assert isinstance(ctx, AppContext)
                assert ctx.client is mock_client
        mock_client.close.assert_awaited_once()


class TestServer:
    def test_main_calls_mcp_run(self) -> None:
        with patch("mcp_docs.app.mcp") as mock_mcp:
            from mcp_docs.server import main

            main()
            mock_mcp.run.assert_called_once()
