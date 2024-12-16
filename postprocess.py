"""Blender script to clean up models from TRELLIS and re-export in different formats."""

import argparse
import sys
from pathlib import Path

import bpy
import mathutils

_ARGS: argparse.Namespace


@bpy.app.handlers.persistent
def _loaded(file_name: str) -> None:
    """Set up the scene once it's loaded.

    This handler needs to be persistent otherwise it'll be reset when the settings are reloaded.
    """
    global _SETTINGS

    if _loaded in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_loaded)

    remesh(_ARGS.input, _ARGS.output)


def remove_base_and_rescale(obj: bpy.types.Object):
    """Identify the base of the miniature."""
    min_x = min(p[0] for p in obj.bound_box)
    max_x = max(p[0] for p in obj.bound_box)
    min_y = min(p[1] for p in obj.bound_box)
    max_y = max(p[1] for p in obj.bound_box)
    min_z = min(p[2] for p in obj.bound_box)
    max_z = max(p[2] for p in obj.bound_box)

    width = max_x - min_x
    depth = max_y - min_y
    height = max_z - min_z
    samples = 100

    top_of_base = min_z

    # Raycast from the top of the object down to find the top of base
    for x_i in range(0, samples):
        x_factor = x_i / samples
        for y_i in range(0, samples):
            y_factor = y_i / samples
            x = min_x + width * x_factor
            y = min_y + depth * y_factor
            origin = mathutils.Vector((x, y, max_z / 5))
            direction = mathutils.Vector((0, 0, -1))
            hit, loc, normal, _ = obj.ray_cast(origin, direction)
            if hit and normal.z > 0.99 and abs(normal.x) + abs(normal.y) < 0.010:
                top_of_base = max(top_of_base, loc.z)
                if top_of_base == loc.z:
                    print(normal)

    bottom_of_base = min_z
    side_of_base = max_x

    # Raycast from the side of the object to find the radius of the base
    for z_i in range(0, samples):
        z_factor = z_i / samples
        origin = mathutils.Vector((min_x, 0, min_z + z_factor * height))
        direction = mathutils.Vector((1, 0, 0))
        hit, loc, _, _ = obj.ray_cast(origin, direction)
        if hit:
            side_of_base = min(side_of_base, loc.x)

    diameter_m = 2 * abs(side_of_base - obj.location.x)

    # Create a cube to subtrace the existing base from the mini
    bpy.ops.mesh.primitive_cube_add(size=1)
    base = bpy.context.object
    base.scale.z = top_of_base - bottom_of_base
    base.scale.x = max(base.scale.x, 2 * diameter_m)
    base.scale.y = max(base.scale.y, 2 * diameter_m)
    base.location = mathutils.Vector(
        (obj.location.x, obj.location.y, bottom_of_base + base.scale.z / 2)
    )

    # Subtract the existing base from the mini
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_add(type="BOOLEAN")
    bpy.context.object.modifiers["Boolean"].operation = "DIFFERENCE"
    bpy.context.object.modifiers["Boolean"].object = base
    bpy.ops.object.modifier_apply(modifier="Boolean")
    bpy.data.objects.remove(base)

    # Scale the mini so that the base is 1 inch in diameter
    obj.scale *= 0.0254 / diameter_m


def add_base(obj: bpy.types.Object):
    """Add a 1 inch diameter base to the miniature."""
    height = 0.002
    bpy.ops.mesh.primitive_cylinder_add(radius=0.0254 / 2, depth=height)
    base = bpy.context.object
    base.name = "Base"
    base.location = mathutils.Vector(
        (
            obj.location.x,
            obj.location.y,
            min(p[2] for p in obj.bound_box) * obj.scale.z - height / 2,
        )
    )


def remesh(input: str, output: str) -> None:
    # Import the GLB
    if input.endswith((".gltf", ".glb")):
        bpy.ops.import_scene.gltf(filepath=input)
    elif input.endswith(".stl"):
        bpy.ops.wm.stl_import(filepath=input)
    else:
        raise ValueError(f"Unsupported input format: {Path(input).suffix}")

    geometry = bpy.data.objects["geometry_0"]

    # Select the geometry object
    geometry.select_set(True)
    bpy.context.view_layer.objects.active = geometry

    # Go into edit mode
    bpy.ops.object.editmode_toggle()

    # Assign all the vertices to a new vertex group
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.object.vertex_group_assign_new()

    # Use a weld operation to fix disconnected parts of the mesh
    bpy.ops.object.modifier_add(type="WELD")
    bpy.context.object.modifiers["Weld"].vertex_group = geometry.vertex_groups[-1].name
    bpy.ops.object.editmode_toggle()  # We can only apply from object mode
    bpy.ops.object.modifier_apply(modifier="Weld")

    # Separate out the loose parts of the mesh
    bpy.ops.object.editmode_toggle()
    bpy.ops.mesh.separate(type="LOOSE")

    bpy.ops.object.editmode_toggle()
    for obj in bpy.context.selected_objects:
        if obj.name != geometry.name:
            bpy.data.objects.remove(obj)

    remove_base_and_rescale(geometry)
    add_base(geometry)

    # Export
    output_suffix = Path(output).suffix
    if output_suffix in frozenset({".glb", ".gltf"}):
        bpy.ops.export_scene.gltf(filepath=output)
    elif output_suffix == ".obj":
        bpy.ops.wm.obj_export(filepath=output)
    elif output_suffix == ".stl":
        bpy.ops.wm.stl_export(filepath=output)
    else:
        raise ValueError(f"Unsupported output format: {output_suffix}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply voxel remesh to a model.")
    parser.add_argument("input", help="Input GLB file path")
    parser.add_argument("output", help="Output GLB file path")
    _ARGS = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])

    bpy.app.handlers.load_factory_startup_post.append(_loaded)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # Disable the welcome splash
    bpy.context.preferences.view.show_splash = False
