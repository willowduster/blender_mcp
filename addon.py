"""
Blender MCP Addon

Installs a lightweight TCP server inside Blender so the MCP server
(server.py) can send Python commands and read scene information.

Installation
------------
1. Edit > Preferences > Add-ons > Install… > select this file
2. Enable "Interface: Blender MCP"
3. Press N in the 3D Viewport → open the "MCP" tab → click "Start MCP Server"
"""

import bpy
import io
import json
import mathutils
import os
import socket
import tempfile
import threading
import traceback

from bpy.props import BoolProperty, IntProperty
from contextlib import redirect_stdout

bl_info = {
    "name": "Blender MCP",
    "author": "blender_mcp",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > MCP",
    "description": "MCP socket server – lets AI chat create Blender scenes",
    "category": "Interface",
}

DEFAULT_PORT = 9876


# ---------------------------------------------------------------------------
# TCP server
# ---------------------------------------------------------------------------

class BlenderMCPServer:
    """Background TCP server that receives JSON commands and executes them in Blender."""

    def __init__(self, host: str = "localhost", port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.running = False
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None

    # --- lifecycle ----------------------------------------------------------

    def start(self):
        if self.running:
            return
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind((self.host, self.port))
            self._socket.listen(5)
            self.running = True
            self._thread = threading.Thread(target=self._accept_loop, daemon=True)
            self._thread.start()
            print(f"[BlenderMCP] Server listening on {self.host}:{self.port}")
        except Exception as exc:
            print(f"[BlenderMCP] Failed to start: {exc}")
            self._close_socket()

    def stop(self):
        self.running = False
        self._close_socket()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        print("[BlenderMCP] Server stopped")

    def _close_socket(self):
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    # --- accept loop (background thread) ------------------------------------

    def _accept_loop(self):
        assert self._socket is not None
        self._socket.settimeout(1.0)
        while self.running:
            try:
                conn, addr = self._socket.accept()
                print(f"[BlenderMCP] Client connected: {addr}")
                threading.Thread(target=self._client_loop, args=(conn,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as exc:
                if self.running:
                    print(f"[BlenderMCP] Accept error: {exc}")
                break

    # --- per-client loop (background thread) --------------------------------

    def _client_loop(self, conn: socket.socket):
        conn.settimeout(None)
        buf = b""
        try:
            while self.running:
                data = conn.recv(65536)
                if not data:
                    break
                buf += data
                try:
                    command = json.loads(buf.decode("utf-8"))
                    buf = b""
                except json.JSONDecodeError:
                    continue  # wait for more bytes

                # Run on Blender's main thread via timer
                def _run(cmd=command, c=conn):
                    try:
                        response = self._dispatch(cmd)
                    except Exception as exc:
                        traceback.print_exc()
                        response = {"status": "error", "message": str(exc)}
                    try:
                        c.sendall(json.dumps(response).encode("utf-8"))
                    except Exception:
                        pass
                    return None  # bpy.app.timers callback must return None

                bpy.app.timers.register(_run, first_interval=0.0)
        except Exception as exc:
            print(f"[BlenderMCP] Client error: {exc}")
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # --- command dispatch ---------------------------------------------------

    def _dispatch(self, command: dict) -> dict:
        handlers = {
            "ping":                   self._ping,
            "get_scene_info":         self._get_scene_info,
            "get_object_info":        self._get_object_info,
            "execute_code":           self._execute_code,
            "get_viewport_screenshot": self._get_viewport_screenshot,
        }
        cmd_type = command.get("type", "")
        params   = command.get("params", {})
        handler  = handlers.get(cmd_type)
        if handler is None:
            return {"status": "error", "message": f"Unknown command: {cmd_type!r}"}
        try:
            return {"status": "success", "result": handler(**params)}
        except Exception as exc:
            traceback.print_exc()
            return {"status": "error", "message": str(exc)}

    # --- command implementations -------------------------------------------

    def _ping(self) -> dict:
        return {"pong": True}

    def _get_scene_info(self) -> dict:
        scene = bpy.context.scene
        objects = []
        for i, obj in enumerate(scene.objects):
            if i >= 20:
                break
            objects.append({
                "name":     obj.name,
                "type":     obj.type,
                "location": [round(obj.location.x, 4),
                              round(obj.location.y, 4),
                              round(obj.location.z, 4)],
                "visible":  obj.visible_get(),
            })
        return {
            "scene_name":      scene.name,
            "object_count":    len(scene.objects),
            "objects":         objects,
            "materials_count": len(bpy.data.materials),
            "frame_current":   scene.frame_current,
            "frame_start":     scene.frame_start,
            "frame_end":       scene.frame_end,
        }

    def _get_object_info(self, name: str) -> dict:
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise ValueError(f"Object '{name}' not found")
        info = {
            "name":           obj.name,
            "type":           obj.type,
            "location":       list(obj.location),
            "rotation_euler": list(obj.rotation_euler),
            "scale":          list(obj.scale),
            "visible":        obj.visible_get(),
            "materials":      [s.material.name for s in obj.material_slots if s.material],
        }
        if obj.type == "MESH" and obj.data:
            m = obj.data
            info["mesh"] = {
                "vertices": len(m.vertices),
                "edges":    len(m.edges),
                "polygons": len(m.polygons),
            }
            corners = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
            info["world_bounding_box"] = [
                [min(v[i] for v in corners) for i in range(3)],
                [max(v[i] for v in corners) for i in range(3)],
            ]
        return info

    def _execute_code(self, code: str) -> dict:
        """Execute code in a namespace seeded with bpy.
        Note: the executed code can import additional modules with standard
        import statements, so this is not a security sandbox — it is
        intentional full Blender Python access.
        """
        out = io.StringIO()
        ns: dict = {}
        with redirect_stdout(out):
            exec(compile(code, "<mcp>", "exec"), {"bpy": bpy}, ns)
        return {"output": out.getvalue(), "result": "Code executed successfully"}

    def _get_viewport_screenshot(
        self,
        max_size: int = 800,
        filepath: str | None = None,
        fmt: str = "png",
    ) -> dict:
        if not filepath:
            filepath = os.path.join(tempfile.gettempdir(), "blender_mcp_shot.png")
        area = next((a for a in bpy.context.screen.areas if a.type == "VIEW_3D"), None)
        if area is None:
            raise RuntimeError("No 3D viewport found")
        with bpy.context.temp_override(area=area):
            bpy.ops.screen.screenshot_area(filepath=filepath)
        img = bpy.data.images.load(filepath)
        w, h = img.size
        if max(w, h) > max_size:
            scale = max_size / max(w, h)
            w, h = int(w * scale), int(h * scale)
            img.scale(w, h)
            img.file_format = fmt.upper()
            img.filepath_raw = filepath
            img.save()
        bpy.data.images.remove(img)
        return {"success": True, "filepath": filepath, "width": w, "height": h}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_server: BlenderMCPServer | None = None

def _get_server() -> BlenderMCPServer:
    global _server
    if _server is None:
        _server = BlenderMCPServer()
    return _server


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class BLENDERMCP_OT_Start(bpy.types.Operator):
    bl_idname = "blendermcp.start"
    bl_label = "Start MCP Server"
    bl_description = "Start listening for MCP commands on localhost:9876"

    def execute(self, context):
        srv = _get_server()
        if srv.running:
            self.report({"WARNING"}, "Already running")
            return {"CANCELLED"}
        srv.port = context.scene.blendermcp_port
        srv.start()
        context.scene.blendermcp_running = srv.running
        if srv.running:
            self.report({"INFO"}, f"MCP server started on port {srv.port}")
        else:
            self.report({"ERROR"}, "Failed to start – check the system console")
        return {"FINISHED"}


class BLENDERMCP_OT_Stop(bpy.types.Operator):
    bl_idname = "blendermcp.stop"
    bl_label = "Stop MCP Server"

    def execute(self, context):
        _get_server().stop()
        context.scene.blendermcp_running = False
        self.report({"INFO"}, "MCP server stopped")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

class BLENDERMCP_PT_Panel(bpy.types.Panel):
    bl_label      = "Blender MCP"
    bl_idname     = "BLENDERMCP_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category   = "MCP"

    def draw(self, context):
        layout  = self.layout
        scene   = context.scene
        running = scene.blendermcp_running

        layout.label(
            text="● Running" if running else "○ Stopped",
            icon="CHECKMARK" if running else "X",
        )
        layout.prop(scene, "blendermcp_port", text="Port")
        layout.separator()
        if running:
            layout.operator("blendermcp.stop",  icon="PAUSE")
        else:
            layout.operator("blendermcp.start", icon="PLAY")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_CLASSES = [BLENDERMCP_OT_Start, BLENDERMCP_OT_Stop, BLENDERMCP_PT_Panel]


def register():
    bpy.types.Scene.blendermcp_port = IntProperty(
        name="Port", default=DEFAULT_PORT, min=1024, max=65535,
    )
    bpy.types.Scene.blendermcp_running = BoolProperty(default=False)
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    print("[BlenderMCP] Addon registered")


def unregister():
    srv = _get_server()
    if srv.running:
        srv.stop()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.blendermcp_port
    del bpy.types.Scene.blendermcp_running
    print("[BlenderMCP] Addon unregistered")


if __name__ == "__main__":
    register()
