"""
Blender MCP Server

Bridges VSCode AI chat (GitHub Copilot, Claude, etc.) to a running Blender
instance via the Model Context Protocol (MCP) stdio transport.

Usage
-----
VSCode / .vscode/mcp.json launches this script automatically.
You can also run it manually:  uv run server.py
"""

from __future__ import annotations

import json
import logging
import os
import socket
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from mcp.server.fastmcp import Context, FastMCP, Image

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("blender_mcp")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9876

# ---------------------------------------------------------------------------
# Blender connection
# ---------------------------------------------------------------------------


@dataclass
class BlenderConnection:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    _sock: socket.socket | None = field(default=None, init=False, repr=False)

    def connect(self) -> bool:
        if self._sock is not None:
            return True
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.host, self.port))
            self._sock = s
            logger.info("Connected to Blender at %s:%s", self.host, self.port)
            return True
        except Exception as exc:
            logger.error("Cannot connect to Blender: %s", exc)
            self._sock = None
            return False

    def disconnect(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def is_connected(self) -> bool:
        return self._sock is not None

    def _recv_until_complete_json(self, timeout: float = 180.0) -> bytes:
        """Read raw bytes from the socket until a complete JSON object has been received."""
        assert self._sock is not None
        self._sock.settimeout(timeout)
        chunks: list[bytes] = []
        while True:
            try:
                chunk = self._sock.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                if not chunks:
                    raise ConnectionError("Blender closed the connection before sending data")
                break
            chunks.append(chunk)
            data = b"".join(chunks)
            try:
                json.loads(data.decode("utf-8"))
                return data
            except json.JSONDecodeError:
                continue
        data = b"".join(chunks)
        if not data:
            raise ConnectionError("No data received from Blender")
        json.loads(data.decode("utf-8"))  # re-raise if still invalid
        return data

    def send_command(self, cmd_type: str, params: dict[str, Any] | None = None) -> Any:
        """Send a command to Blender and return its result payload."""
        if not self._sock and not self.connect():
            raise ConnectionError(
                "Not connected to Blender. "
                "Open Blender → MCP panel (N-key) → Start MCP Server."
            )
        payload = json.dumps({"type": cmd_type, "params": params or {}}).encode()
        try:
            self._sock.sendall(payload)  # type: ignore[union-attr]
            raw = self._recv_until_complete_json()
            response: dict = json.loads(raw.decode("utf-8"))
        except socket.timeout:
            self._sock = None
            raise TimeoutError("Blender did not respond in time. Try a smaller request.")
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as exc:
            self._sock = None
            raise ConnectionError(f"Lost connection to Blender: {exc}") from exc
        except json.JSONDecodeError as exc:
            self._sock = None
            raise ValueError(f"Blender sent invalid JSON: {exc}") from exc
        except Exception as exc:
            self._sock = None
            raise RuntimeError(f"Blender communication error: {exc}") from exc

        if response.get("status") == "error":
            raise RuntimeError(response.get("message", "Unknown error from Blender"))
        return response.get("result", {})


# ---------------------------------------------------------------------------
# Shared connection
# ---------------------------------------------------------------------------

_blender: BlenderConnection | None = None


def get_blender() -> BlenderConnection:
    """Return a live connection to Blender, reconnecting if needed."""
    global _blender

    if _blender is not None and _blender.is_connected():
        try:
            _blender.send_command("ping")
            return _blender
        except Exception as exc:
            logger.warning("Stale connection (%s) – reconnecting…", exc)
            _blender.disconnect()
            _blender = None

    host = os.getenv("BLENDER_HOST", DEFAULT_HOST)
    port = int(os.getenv("BLENDER_PORT", DEFAULT_PORT))
    conn = BlenderConnection(host=host, port=port)
    if not conn.connect():
        raise ConnectionError(
            "Cannot reach Blender. "
            "Open Blender, install addon.py, and click 'Start MCP Server' in the MCP panel."
        )
    _blender = conn
    return _blender


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[dict]:
    logger.info("BlenderMCP server starting…")
    try:
        get_blender()
        logger.info("Connected to Blender")
    except Exception as exc:
        logger.warning("Blender not reachable at startup: %s", exc)
    yield {}
    global _blender
    if _blender:
        _blender.disconnect()
        _blender = None
    logger.info("BlenderMCP server stopped")


mcp = FastMCP("BlenderMCP", lifespan=_lifespan)

# ---------------------------------------------------------------------------
# Resource – live scene snapshot
# ---------------------------------------------------------------------------


@mcp.resource("blender://scene")
def scene_resource() -> str:
    """Live JSON snapshot of the current Blender scene."""
    return json.dumps(get_blender().send_command("get_scene_info"), indent=2)


# ---------------------------------------------------------------------------
# Tool – inspect the scene
# ---------------------------------------------------------------------------


@mcp.tool()
def get_scene_info(ctx: Context) -> str:
    """
    Return a JSON summary of the current Blender scene (object list, material
    count, animation frame range).  Use this to understand what is already in
    the scene before making changes.
    """
    try:
        return json.dumps(get_blender().send_command("get_scene_info"), indent=2)
    except Exception as exc:
        return f"Error: {exc}"


@mcp.tool()
def get_object_info(ctx: Context, object_name: str) -> str:
    """
    Return detailed JSON information about one named object: transform, mesh
    statistics, materials, and world-space bounding box.

    Parameters
    ----------
    object_name : str
        Exact name of the object as it appears in the Blender outliner.
    """
    try:
        result = get_blender().send_command("get_object_info", {"name": object_name})
        return json.dumps(result, indent=2)
    except Exception as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool – see the viewport
# ---------------------------------------------------------------------------


@mcp.tool()
def get_viewport_screenshot(ctx: Context, max_size: int = 800) -> Image:
    """
    Capture and return a screenshot of the Blender 3D viewport so you can
    visually verify the scene after making changes.

    Parameters
    ----------
    max_size : int
        Maximum pixel dimension of the returned image (default 800).
    """
    tmp = os.path.join(tempfile.gettempdir(), "blender_mcp_shot.png")
    get_blender().send_command(
        "get_viewport_screenshot",
        {"max_size": max_size, "filepath": tmp, "fmt": "png"},
    )
    if not os.path.exists(tmp):
        raise FileNotFoundError("Blender did not create the screenshot file")
    with open(tmp, "rb") as fh:
        data = fh.read()
    try:
        os.remove(tmp)
    except OSError:
        pass
    return Image(data=data, format="png")


# ---------------------------------------------------------------------------
# Tool – build / modify the scene
# ---------------------------------------------------------------------------


@mcp.tool()
def execute_blender_code(ctx: Context, code: str) -> str:
    """
    Execute Python code directly inside Blender to create or modify the scene.

    This is the primary tool for scene creation.  Write standard Blender
    Python (bpy) to add meshes, lights, cameras, materials, modifiers,
    animations, or anything else the Blender API supports.

    Guidelines
    ----------
    - `bpy` is already imported in the execution namespace.
    - Import other modules you need at the top of the code block.
    - Use `print(...)` to emit diagnostic text that will be returned here.
    - For large scenes, break the work into multiple sequential calls.
    - Call `bpy.context.view_layer.update()` after bulk object transforms.

    Parameters
    ----------
    code : str
        Valid Python 3 code to run inside Blender.
    """
    try:
        result = get_blender().send_command("execute_code", {"code": code})
        output = result.get("output", "")
        status = result.get("result", "Code executed successfully")
        return f"{status}\n{output}".strip()
    except Exception as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
