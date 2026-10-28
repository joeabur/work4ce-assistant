"""Reference transport adapters. Only trusted packaged demo endpoints are allowed."""
import asyncio
import hashlib
import json
import sys
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from jsonschema import Draft202012Validator, FormatChecker
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import Tool

from .fixtures import SEARCH_CAPABILITY

MAX_BYTES = 262144


class ConnectorError(RuntimeError):
    """Redacted connector failure safe to expose to trusted orchestration."""


def _validate(arguments: dict, output: bool = False) -> None:
    schema = SEARCH_CAPABILITY["output_schema" if output else "input_schema"]
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(arguments)
    if len(json.dumps(arguments).encode()) > MAX_BYTES:
        raise ConnectorError("Connector payload exceeds budget")


def _fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class RestConnector:
    def __init__(self, base_url: str):
        parsed = urlsplit(base_url)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username
                or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or parsed.port is None):
            raise ValueError("Demo REST endpoint must be explicit http://127.0.0.1:PORT")
        self.base_url = base_url.rstrip("/")
        self._pinned: str | None = None

    async def _request(self, method: str, path: str, **kwargs) -> object:
        # trust_env=False is limited to this fixed loopback synthetic service.
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False) as client:
                async with client.stream(method, self.base_url + path, **kwargs) as response:
                    response.raise_for_status()
                    data = bytearray()
                    async for part in response.aiter_bytes():
                        data.extend(part)
                        if len(data) > MAX_BYTES:
                            raise ConnectorError("Connector payload exceeds budget")
                    return json.loads(data)
        except (httpx.HTTPError, ValueError) as exc:
            raise ConnectorError("REST request failed") from exc

    async def discover(self) -> list[dict]:
        value = await self._request("GET", "/capabilities")
        if value != [SEARCH_CAPABILITY]:
            raise ConnectorError("REST capability definition not approved")
        fingerprint = _fingerprint(value)
        if self._pinned is not None and self._pinned != fingerprint:
            raise ConnectorError("REST capability definition changed")
        self._pinned = fingerprint
        return deepcopy(value)

    async def health(self) -> bool:
        try:
            return await self._request("GET", "/health") == {"status": "ok", "synthetic": True}
        except Exception:
            return False

    async def invoke(self, capability_id: str, arguments: dict) -> dict:
        if capability_id != SEARCH_CAPABILITY["capability_id"] or self._pinned is None:
            raise ConnectorError("Capability not registered")
        _validate(arguments)
        await self.discover()
        output = await self._request("POST", "/events/search", json=arguments)
        _validate(output, output=True)
        return output


class McpConnector:
    """Official MCP SDK stdio adapter with fixed executable and reviewed tool mapping."""
    def __init__(self):
        self._pinned: str | None = None
        self.protocol_version: str | None = None

    @asynccontextmanager
    async def _session(self):
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "work4ce_assistant.reference_servers", "mcp"],
            env={"PYTHONPATH": str(Path(__file__).resolve().parents[1])},
        )
        async with asyncio.timeout(10):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=5)) as session:
                    initialized = await session.initialize()
                    self.protocol_version = initialized.protocolVersion
                    yield session

    async def _check_tools(self, session: ClientSession) -> None:
        result = await session.list_tools()
        expected = Tool(name="search_events", description=SEARCH_CAPABILITY["description"],
                        inputSchema=SEARCH_CAPABILITY["input_schema"], outputSchema=SEARCH_CAPABILITY["output_schema"])
        actual = [tool.model_dump(mode="json", by_alias=True) for tool in result.tools]
        if result.nextCursor is not None or actual != [expected.model_dump(mode="json", by_alias=True)]:
            raise ConnectorError("MCP tool definition not approved")
        fingerprint = _fingerprint(actual)
        if self._pinned is not None and self._pinned != fingerprint:
            raise ConnectorError("MCP tool definition changed")
        self._pinned = fingerprint

    async def discover(self) -> list[dict]:
        async with self._session() as session:
            await self._check_tools(session)
        return [deepcopy(SEARCH_CAPABILITY)]

    async def health(self) -> bool:
        try:
            async with self._session() as session:
                await session.send_ping()
            return True
        except Exception:
            return False

    async def invoke(self, capability_id: str, arguments: dict) -> dict:
        if capability_id != SEARCH_CAPABILITY["capability_id"] or self._pinned is None:
            raise ConnectorError("Capability not registered")
        _validate(arguments)
        async with self._session() as session:
            await self._check_tools(session)
            result = await session.call_tool("search_events", arguments)
            if result.isError or result.structuredContent is None:
                raise ConnectorError("MCP tool invocation failed")
            output = result.structuredContent
            _validate(output, output=True)
            return output
