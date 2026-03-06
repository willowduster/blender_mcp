"""
sprite_to_voxel.py
------------------
Converts a pixel-art sprite PNG into an extruded 3D voxel model in Blender.

Usage (from Blender's scripting tab or via blender --python):
    1. Set IMAGE_PATH to the path of your sprite PNG.
    2. Set OUTPUT_BLEND to where you want the .blend saved.
    3. Run via:  blender --background --python scripts/sprite_to_voxel.py

Dependencies (for the image analysis step):
    pip install pillow  (or: uv run python scripts/sprite_to_voxel.py --analyze-only)

The script has two phases:
    Phase 1 - Image analysis: samples the PNG at BLOCK_SIZE resolution,
              classifies each pixel by majority vote, and produces a grid dict.
    Phase 2 - Blender generation: places extruded cubes per pixel, sets up
              materials, lighting and camera, then saves the .blend file.
"""

import sys
import os
import math

# ── Configuration ────────────────────────────────────────────────────────────
IMAGE_PATH   = r"C:\Users\Willow\Documents\code\blender_mcp\willowduster.png"
OUTPUT_BLEND = r"C:\Users\Willow\Documents\code\blender_mcp\output\willowduster.blend"
BLOCK_SIZE   = 32   # px per sprite pixel (1024 / 32 = 32×32 sprite)
VOXEL_SIZE   = 1.0  # Blender units per pixel
VOXEL_DEPTH  = 2.0  # extrusion depth
# ─────────────────────────────────────────────────────────────────────────────


# ── Phase 1: Image Analysis ───────────────────────────────────────────────────
def analyze_sprite(image_path, block_size):
    """
    Sample a pixel-art sprite PNG at `block_size` intervals using a 5×5
    interior majority vote per block.

    Returns a dict: { row: { col: 'B'|'D'|'E' } }
      B = black outline
      D = dark grey (robe body)
      E = emissive green gem
    """
    from PIL import Image
    from collections import Counter

    img = Image.open(image_path).convert("RGBA")
    side = img.width // block_size  # assumes square image

    def classify(r, g, b, a):
        if a < 30:
            return None
        if r > 220 and g > 220 and b > 220:
            return None           # white / transparent background
        if g > 120 and r < 80 and b < 80:
            return "E"            # bright green gem  (0, 255, 47)
        if r < 40 and g < 40 and b < 40:
            return "B"            # pure black outline
        return "D"                # dark grey robe body (70, 70, 70)

    rows_data = {}
    for row in range(side):
        row_dict = {}
        for col in range(side):
            votes = []
            for dy in range(5):
                for dx in range(5):
                    px = col * block_size + 3 + dx * (block_size - 6) // 4
                    py = row * block_size + 3 + dy * (block_size - 6) // 4
                    c = classify(*img.getpixel((px, py)))
                    if c:
                        votes.append(c)
            if votes:
                row_dict[col] = Counter(votes).most_common(1)[0][0]
        if row_dict:
            rows_data[row] = row_dict

    return rows_data, side


# ── Phase 2: Blender Scene Generation ────────────────────────────────────────
def build_voxel_scene(rows_data, grid_side, voxel_size, depth, output_path):
    import bpy
    import mathutils

    # -- Clear scene --
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)

    # -- Materials --
    def mk_bsdf(name, rgb):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = (*rgb, 1)
        bsdf.inputs["Roughness"].default_value = 0.9
        try:
            bsdf.inputs["Specular IOR Level"].default_value = 0.05
        except KeyError:
            pass
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        return m

    def mk_emit(name, rgb, strength=5.0):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (*rgb, 1)
        em.inputs["Strength"].default_value = strength
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        return m

    M_BLK = mk_bsdf("Black", (0.01,  0.01,  0.01))
    M_GRY = mk_bsdf("Grey",  (0.274, 0.274, 0.274))
    M_GEM = mk_emit("Gem",   (0.0,   1.0,   0.184), strength=5.0)
    MAT   = {"B": M_BLK, "D": M_GRY, "E": M_GEM}

    V  = voxel_size
    cx = (grid_side - 1) / 2.0

    # -- Place voxels --
    for row, cols in rows_data.items():
        for col, mkey in cols.items():
            x = (col - cx) * V
            z = (grid_side - 1 - row) * V + V / 2
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, depth / 2, z))
            obj = bpy.context.active_object
            obj.scale = (V * 0.98, depth * 0.5, V * 0.98)
            bpy.ops.object.transform_apply(scale=True)
            obj.data.materials.append(MAT[mkey])

    # -- Camera (3/4 perspective view) --
    bpy.ops.object.camera_add(location=(45, -55, 45))
    cam = bpy.context.active_object
    cam.name = "Camera"
    cam.data.type = "PERSP"
    cam.data.lens = 70
    target    = mathutils.Vector((0, depth / 2, (grid_side / 2) * V))
    direction = target - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam

    # -- Lights --
    bpy.ops.object.light_add(type="AREA", location=(-15, -25, 30))
    key = bpy.context.active_object
    key.data.energy = 2000
    key.data.size   = 12
    key.data.color  = (1.0, 0.97, 0.9)
    key.rotation_euler = (math.radians(40), 0, math.radians(-25))

    bpy.ops.object.light_add(type="AREA", location=(25, -10, 15))
    fill = bpy.context.active_object
    fill.data.energy = 600
    fill.data.size   = 10
    fill.data.color  = (0.7, 0.8, 1.0)
    fill.rotation_euler = (math.radians(30), 0, math.radians(70))

    bpy.ops.object.light_add(type="POINT", location=(8, 18, 12))
    rim = bpy.context.active_object
    rim.data.energy = 800
    rim.data.color  = (0.0, 1.0, 0.18)

    # -- World --
    world = bpy.context.scene.world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value    = (0.02, 0.02, 0.03, 1)
        bg.inputs["Strength"].default_value = 0.2

    # -- Render settings --
    bpy.context.scene.render.resolution_x = 1080
    bpy.context.scene.render.resolution_y = 1080
    try:
        bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        bpy.context.scene.render.engine = "BLENDER_EEVEE"

    # -- Save --
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=output_path)
    print(f"Saved: {output_path}")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Analyzing sprite: {IMAGE_PATH} (block size: {BLOCK_SIZE}px)")
    rows_data, grid_side = analyze_sprite(IMAGE_PATH, BLOCK_SIZE)
    print(f"Grid: {grid_side}×{grid_side}, filled pixels: {sum(len(v) for v in rows_data.values())}")

    print("Building voxel scene in Blender...")
    build_voxel_scene(rows_data, grid_side, VOXEL_SIZE, VOXEL_DEPTH, OUTPUT_BLEND)
