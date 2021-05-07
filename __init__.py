bl_info = {
    "name": "ERNE IFC Void Data",
    "author": "Frederic Beaupere",
    "description": "IFC void data aggregation",
    "blender": (2, 91, 0),
    "category": "Generic",
    "location": "View3D",
    "warning": "",
    "repo_url": "https://github.com/erneagholzbau/ifc_void_data",
    "docs_url": "https://github.com/erneagholzbau/ifc_void_data/wiki",
    "version": "2021.01.20",
}

import bpy
from . import ui


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


classes = (
    ui.IVD_PT_docs,
    ui.IVD_PT_models,
    ui.IVD_PT_calc,
    ui.IVD_OT_docs,
    ui.IVD_OT_reset_paths,
    ui.IVD_OT_set_path,
    ui.IVD_OT_run_calc,
    ui.IVD_OT_open_csv,
)

if __name__ == "__main__":
    register()
