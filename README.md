# Blender MCP

Describe a 3D scene or model in plain English inside your **VSCode chat window** and watch it appear in Blender in real time.  No Blender experience required — just type what you want.

---

## Table of contents

1. [How it works](#how-it-works)
2. [Requirements](#requirements)
3. [Installation](#installation)
   - [Step 1 — Install uv](#step-1--install-uv)
   - [Step 2 — Get the files](#step-2--get-the-files)
   - [Step 3 — Install the Blender addon](#step-3--install-the-blender-addon)
   - [Step 4 — Open the project in VSCode](#step-4--open-the-project-in-vscode)
   - [Step 5 — Enable the MCP server in VSCode](#step-5--enable-the-mcp-server-in-vscode)
4. [Every-session startup](#every-session-startup)
5. [Writing prompts](#writing-prompts)
6. [Example prompts](#example-prompts)
7. [Available tools (reference)](#available-tools-reference)
8. [Changing the port](#changing-the-port)
9. [Troubleshooting](#troubleshooting)
10. [Security note](#security-note)

---

## How it works

```
Your words
   │
   ▼
VSCode Chat (AI agent)
   │  MCP stdio
   ▼
server.py                 ← runs on your PC, launched by VSCode
   │  TCP localhost:9876
   ▼
Blender addon (addon.py)  ← runs inside Blender
   │
   ▼
Blender viewport          ← you watch it happen
```

1. You type a description in VSCode chat.
2. The AI translates it into Blender Python (`bpy`) and calls the `execute_blender_code` tool.
3. `server.py` forwards the code to the addon over a local socket.
4. The addon runs the code on Blender's main thread — objects appear in the viewport immediately.
5. The AI calls `get_viewport_screenshot` to see the result, then refines until it matches your description.

---

## Requirements

| What | Version / Notes |
|---|---|
| **Windows** | 10 or 11, 64-bit |
| **Blender** | 4.0 or newer (tested with Blender 5) — [download](https://www.blender.org/download/) |
| **Python** | 3.10 or newer — only used by `server.py`; Blender ships its own Python internally |
| **uv** | Python package manager — used to install dependencies and launch the server |
| **VSCode** | [download](https://code.visualstudio.com/) |
| **GitHub Copilot extension** | [install from marketplace](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot) — provides the AI chat with MCP support |

---

## Installation

Do this once.  After setup is complete, each session only needs [two clicks](#every-session-startup).

### Step 1 — Install uv

Open **PowerShell** and run:

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then add `uv` to your user PATH so VSCode can find it:

```powershell
$localBin = "$env:USERPROFILE\.local\bin"
$userPath  = [Environment]::GetEnvironmentVariable("Path", "User")
[Environment]::SetEnvironmentVariable("Path", "$userPath;$localBin", "User")
```

Close and reopen any terminals / VSCode windows after running this.

Verify the install:

```powershell
uv --version
```

---

### Step 2 — Get the files

Clone or download this repository to a folder on your PC, for example `C:\blender_mcp`:

```powershell
git clone https://github.com/willowduster/blender_mcp.git C:\blender_mcp
```

Or download the ZIP from GitHub and extract it to `C:\blender_mcp`.

The relevant files are:

```
C:\blender_mcp\
├── addon.py          ← install this into Blender
├── server.py         ← VSCode launches this automatically
├── pyproject.toml    ← dependency list (uv reads this)
└── .vscode\
    └── mcp.json      ← tells VSCode how to start the server
```

---

### Step 3 — Install the Blender addon

1. Open **Blender**.
2. Go to **Edit → Preferences** (top-left menu).
3. Click **Add-ons** in the left sidebar.
4. Click **Install…** (top-right of the Add-ons panel).
5. Navigate to `C:\blender_mcp\addon.py` and click **Install Add-on**.
6. In the search box type **MCP**.  You should see **"Interface: Blender MCP"**.
7. **Tick the checkbox** to enable it.
8. Close Preferences.

> **Tip:** Blender remembers installed addons between sessions.  You only need to do this once.

---

### Step 4 — Open the project in VSCode

1. Open **VSCode**.
2. **File → Open Folder…** and select `C:\blender_mcp`.

   VSCode will detect the `.vscode/mcp.json` file automatically.  This file tells VSCode to launch `server.py` with `uv` whenever the MCP server is needed:

   ```json
   {
     "servers": {
       "blender-mcp": {
         "type": "stdio",
         "command": "uv",
         "args": ["run", "server.py"]
       }
     }
   }
   ```

   You do not need to edit this file.

---

### Step 5 — Enable the MCP server in VSCode

1. Open the **Command Palette** (`Ctrl+Shift+P`).
2. Type **MCP** and select **"MCP: List Servers"**.
3. You should see **blender-mcp** listed.  If it shows as *stopped*, click the ▶ button next to it to start it.

   Alternatively, just open a Copilot Chat window — VSCode starts the MCP server automatically when the chat is opened in Agent mode.

> **Tip:** The MCP server connects to Blender over `localhost:9876`.  If Blender is not yet running, the server will start but will tell you to open Blender when you send your first prompt.

---

## Every-session startup

After the one-time installation above, each new session is just two steps:

**1.  Start the Blender addon server**

1. Open **Blender**.
2. In the **3D Viewport**, press **N** to open the side panel (the narrow panel on the right).
3. Click the **"MCP"** tab.
4. Click **"Start MCP Server"**.
   The status line changes to **● Running**.

   > If you closed and reopened Blender, you need to click Start again each time.

**2.  Open VSCode and start chatting**

1. Open VSCode with the `C:\blender_mcp` folder.
2. Open **Copilot Chat** (`Ctrl+Alt+I` or click the chat icon in the sidebar).
3. Switch to **Agent mode** — click the dropdown next to the send button and select **Agent**.
4. Type your scene description and press **Enter**.

---

## Writing prompts

You can describe scenes at any level of detail.  The AI will ask for clarification if needed, or make reasonable artistic choices when you leave things open.

**Be as specific or as vague as you like:**

- *Vague:* `"A cozy living room"`
- *Specific:* `"A cozy living room at night: wooden floor, a brick fireplace with orange light, one sofa facing it, and a single overhead lamp casting warm shadows"`

**Reference real-world styles:**

- `"Pixar-style low-poly forest"`
- `"Brutalist concrete tower, photorealistic materials"`
- `"Isometric game scene, pastel colours"`

**Give feedback and iterate:**

After the AI builds the initial scene, you can keep chatting to refine it:

- `"Make the trees taller and add snow on the ground"`
- `"The lighting is too bright — dim it and add a blue tint"`
- `"Rotate the camera 45 degrees and render a preview"`

**Ask for animations:**

- `"Animate the camera slowly orbiting the scene over 250 frames"`
- `"Make the torch flame flicker by animating the light intensity"`

**Ask the AI to check its work:**

- `"Take a screenshot so I can see what it looks like"`
- `"Show me the current scene"`

---

## Example prompts

Below are ready-to-use prompts you can paste straight into the chat.

---

**Simple object**
```
Create a smooth white ceramic vase on a dark wooden table, lit by a single soft rectangular area light from the upper left.
```

---

**Environment / landscape**
```
Build a mountain valley scene: rocky grey peaks in the background, a green grassy floor with a winding river, a few pine trees, and a bright midday sun with volumetric haze.
```

---

**Architecture**
```
Model a small medieval stone chapel: arched entrance, a short bell tower, crumbling walls with ivy, and a cobblestone path leading to the door. Overcast sky.
```

---

**Abstract / artistic**
```
Create an abstract sculpture made of 12 interlocking torus shapes in different sizes, arranged in a spiral. Give each one a different metallic colour and add a studio HDRI-style three-point light rig.
```

---

**Character / creature (low-poly)**
```
Make a low-poly cartoon fox: orange body, white chest, black legs. Pose it sitting with its tail curled around its feet. Add a simple pastel pink background plane.
```

---

**Animation**
```
Set up a 120-frame animation where a red cube falls from Z=5 onto a grey ground plane, squashes slightly on impact at frame 60, then bounces twice with decreasing height.
```

---

**Clear and rebuild**
```
Delete everything in the scene and start fresh: create a simple product-shot setup with a white curved background, a reflective sphere in the centre, and three-point studio lighting.
```

---

## Available tools (reference)

These are the tools the AI uses automatically.  You never need to call them yourself, but knowing what they do can help you write better prompts.

| Tool | What it does |
|---|---|
| `execute_blender_code` | Sends Python (`bpy`) code to run inside Blender — this is how all objects, materials, and animations are created |
| `get_scene_info` | Returns a JSON list of every object in the scene with its name, type, location, and visibility |
| `get_object_info` | Returns detailed data for one named object: full transform, mesh statistics, materials, and world-space bounding box |
| `get_viewport_screenshot` | Captures the current 3D viewport and returns it as an image so the AI can see and react to what Blender looks like |

---

## Changing the port

The default port is **9876**.  If something else on your machine uses that port:

1. In Blender's **MCP panel**, change the **Port** number before clicking Start.
2. In `.vscode/mcp.json`, update the `BLENDER_PORT` environment variable to match:

```json
{
  "servers": {
    "blender-mcp": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "server.py"],
      "env": {
        "BLENDER_HOST": "localhost",
        "BLENDER_PORT": "9877"
      }
    }
  }
}
```

---

## Troubleshooting

**"Cannot connect to Blender" / "Not connected to Blender"**

- Make sure Blender is open.
- Go to the **MCP panel** (N-key in the 3D Viewport → MCP tab) and check the status shows **● Running**.  If it shows *Stopped*, click **Start MCP Server**.
- Make sure the port in the MCP panel matches `BLENDER_PORT` in `.vscode/mcp.json` (both default to `9876`).

---

**Tools don't appear in the Copilot Chat toolbar**

- Make sure you are in **Agent mode** (not Ask or Edit mode) — click the dropdown next to the send button.
- Open the Command Palette (`Ctrl+Shift+P`) → **"MCP: List Servers"** → check that *blender-mcp* is listed and running.
- If the server is listed but stopped, click ▶ to start it, or reload VSCode (`Ctrl+Shift+P` → **"Developer: Reload Window"**).
- Make sure you opened the `C:\blender_mcp` folder (not just a single file) so VSCode can find `.vscode/mcp.json`.

---

**"uv: command not found" or VSCode cannot start the server**

- Run `uv --version` in a new PowerShell window.  If it fails, re-run the installer from [Step 1](#step-1--install-uv) and restart VSCode.
- Make sure you added `uv` to the user PATH as shown in Step 1.

---

**Timeout errors**

- Complex scenes can take time.  Try breaking your request into smaller steps, e.g. first ask for the geometry, then the materials, then the lighting.

---

**Blender becomes unresponsive during code execution**

- Very large mesh operations (high-poly sculpts, dense particle systems) can block Blender briefly.  Wait a few seconds; it will recover.
- If Blender freezes, press **Esc** or use Task Manager to close it, then reopen and restart the addon server.

---

**Changes appear in Blender but the AI says there was an error**

- This can happen if the code printed an error but still partially executed.  Ask the AI: `"Take a screenshot and tell me what is in the scene"` to resync its understanding.

---

**I accidentally deleted everything**

- Use **Ctrl+Z** in Blender to undo.  Blender's undo history is per-session and is separate from the MCP connection.

---

## Security note

`execute_blender_code` runs arbitrary Python inside your running Blender process.  That means it has the same access your user account does — it can read and write files, launch processes, etc.

- Only use this tool with AI models and chat sessions you trust.
- **Save your `.blend` file before starting a session** (`Ctrl+S` in Blender).
- Do not paste untrusted code snippets into the chat and ask the AI to run them.
- The socket server only listens on `localhost` — it is not accessible from other machines on your network.
