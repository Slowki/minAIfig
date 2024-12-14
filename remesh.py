"""Blender script to clean up models from TRELLIS and re-export in different formats."""

import argparse
import sys
from pathlib import Path

import bpy

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


def remesh(input: str, output: str) -> None:
    # Import the GLB
    bpy.ops.import_scene.gltf(filepath=input)

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
