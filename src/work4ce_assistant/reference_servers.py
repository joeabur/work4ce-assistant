"""Trusted demonstration servers. Start only on loopback; synthetic data only."""
import argparse
import asyncio

from fastapi import FastAPI, HTTPException
from jsonschema import ValidationError
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool

from .fixtures import SEARCH_CAPABILITY, search_events

rest_app = FastAPI(title="Work4ce synthetic events")


@rest_app.get("/health")
def health() -> dict:
    return {"status": "ok", "synthetic": True}


@rest_app.get("/capabilities")
def capabilities() -> list[dict]:
    return [SEARCH_CAPABILITY]


@rest_app.post("/events/search")
def search(arguments: dict) -> dict:
    try:
        return search_events(arguments)
    except ValidationError:
        raise HTTPException(status_code=422, detail="Invalid search arguments") from None


server = Server("work4ce-demo-events")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [Tool(name="search_events", description=SEARCH_CAPABILITY["description"],
                 inputSchema=SEARCH_CAPABILITY["input_schema"], outputSchema=SEARCH_CAPABILITY["output_schema"])]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> dict:
    if name != "search_events":
        raise ValueError("Tool not allowed")
    return search_events(arguments)


async def run_mcp() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transport", choices=["mcp", "rest"])
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    if args.transport == "mcp":
        asyncio.run(run_mcp())
    else:
        import uvicorn
        uvicorn.run(rest_app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
