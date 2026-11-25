"""Настоящий Python MCP-клиент, запускающий отдельный процесс через stdio."""
import json
import os
import sys
from pathlib import Path
from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]


def connect():
    return Client(StdioServerParameters(command=sys.executable, args=[str(ROOT / "server.py")],
                                        env=dict(os.environ)), read_timeout_seconds=180)


async def call(client, name, arguments):
    result = await client.call_tool(name, arguments)
    data = result.structured_content
    if data is None:
        text = result.content[0].text
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"message": text}
    return dict(isError=bool(result.is_error), data=data)
