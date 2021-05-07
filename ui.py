import bpy
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from . import bl_info
from . import voids
from pathlib import Path
import datetime
import webbrowser
import re
import os


class IVD_PT_docs(bpy.types.Panel):
    bl_idname = "IVD_PT_docs"
    bl_label = "ERNE IFC Void Data"
    bl_category = "IFC Void Data"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
        layout.label(text=f"welcome to {bl_info['name']}! (version: {bl_info['version']})")
        layout.operator("voids.get_docs", text="open documentation in browser")


class IVD_PT_models(bpy.types.Panel):
    bl_idname = "IVD_PT_models"
    bl_label = "IFC model paths"
    bl_category = "IFC Void Data"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout

        layout.label(text="void model (required):")
        name = "AU"
        void_btn_txt = get_path_button_txt(name)
        op_void = layout.operator("voids.set_path", text=void_btn_txt)
        op_void.discipline = name

        layout.label(text="arc model:")
        name = "A"
        void_btn_txt = get_path_button_txt(name)
        op_arc = layout.operator("voids.set_path", text=void_btn_txt)
        op_arc.discipline = name

        layout.label(text="engineering models:")
        for discipline in eng_models:
            void_btn_txt = get_path_button_txt(discipline)
            op_engineering = layout.operator(
                "voids.set_path",
                text=void_btn_txt
            )
            op_engineering.discipline = discipline

        layout.label(text="directory path instead of single model paths:")
        name = "DIR"
        void_btn_txt = get_path_button_txt(name)
        op_dir = layout.operator("voids.set_path", text=void_btn_txt)
        op_dir.discipline = name

        layout.label(text="set models:")
        for discipline, path in model_paths.items():
            if path:
                dis_row = layout.row()
                dis_row.label(text=f"{discipline} :")
                dis_row.label(text=path.name)

        layout.operator("voids.reset_paths", text="reset found paths")


class IVD_OT_docs(bpy.types.Operator):
    """opens documentation in browser"""
    bl_idname = "voids.get_docs"
    bl_label = "void calculation documentation"
    bl_description = "get void calculation documentation"

    def execute(self, context):
        url = bl_info["docs_url"]
        bpy.ops.wm.read_homefile(app_template="")
        # webbrowser.open(url)
        self.report({'OPERATOR'}, f"{bl_info['name']}: opened docs in browser: {url}")
        return {"FINISHED"}


class IVD_OT_reset_paths(bpy.types.Operator):
    """resets IFC paths"""
    bl_idname = "voids.reset_paths"
    bl_label = "void calculation documentation"
    bl_description = "get void calculation documentation"

    def execute(self, context):
        for k, v in model_paths.items():
            model_paths[k] = None
        self.report({'INFO'}, f"{bl_info['name']}: reset model found paths")
        return {"FINISHED"}


class IVD_OT_set_path(bpy.types.Operator, ImportHelper):
    """set IFC directory or individual IFC model paths"""
    bl_idname = "voids.set_path"
    bl_label = "Set IFC Path"

    filename_ext = ".ifc"
    filter_glob: StringProperty(
        default="*.ifc",
        options={'HIDDEN'},
        maxlen=255,  # Max internal buffer length, longer would be clamped.
    )
    discipline : bpy.props.StringProperty(name="discipline")
    model_path : bpy.props.StringProperty(name="model path")

    def execute(self, context):
        if Path(self.filepath).exists():
            model_paths[self.discipline] = Path(self.filepath)
            if self.discipline == "DIR":
                find_models(self.filepath)
        self.report({'OPERATOR'}, f"{bl_info['name']}: set model path: {self.filepath}")
        return {'FINISHED'}


class IVD_PT_calc(bpy.types.Panel):
    bl_idname = "IVD_PT_calc"
    bl_label = "IFC Void Data Aggregation"
    bl_category = "IFC Void Data"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
        layout.label(text="run void calculations:")
        layout.operator("voids.run_calc", text="run void data aggregation & calculations")
        layout.operator("voids.open_csv", text="open result csv")


class IVD_OT_run_calc(bpy.types.Operator):
    """runs void calculations with defined models"""
    bl_idname = "voids.run_calc"
    bl_label = "void calculation operator"
    bl_description = "runs void calculation"

    def execute(self, context):
        global csv_path
        if not any(model_paths.values()):
            self.bl_info("no models found!", lvl="WARNING")
            return {"FINISHED"}
        if not model_paths["AU"]:
            self.bl_info("no void model found!", lvl="WARNING")
            return {"FINISHED"}

        today_iso_short = str(datetime.datetime.now().date()).replace("-", "")
        csv_path = model_paths["AU"].parent / f"{today_iso_short}_voids.csv"

        found_model_paths = {k:v for k,v in model_paths.items() if v}
        found_eng_models_paths = {k:v for k,v in model_paths.items() if v and k in eng_models}

        self.bl_info(f"---- void process on the following models:")
        for dis, model in found_model_paths.items():
            self.bl_info(f"---- {dis:3} : {model}")

        voids.process_ifc_models(found_model_paths, found_eng_models_paths)

        self.bl_info("calculation successful!", lvl="OPERATOR")
        self.bl_info(f"csv output should be at: {csv_path}", lvl="OPERATOR")
        return {"FINISHED"}

    def bl_info(cls, text, lvl=None):
        lvl = "INFO" if not lvl else lvl
        cls.report({lvl}, f"{bl_info['name']}: {text}")


class IVD_OT_open_csv(bpy.types.Operator):
    """opens calculation csv"""
    bl_idname = "voids.open_csv"
    bl_label = "open calculation csv"
    bl_description = "open calculation csv"

    def execute(self, context):
        if not model_paths["AU"]:
            print("no calculation csv for today found")
            self.bl_info("no calculation csv for today found!", lvl="WARNING")
            return {"FINISHED"}
        os.popen(str(csv_path))
        self.report({'OPERATOR'}, f"{bl_info['name']}: opened csv: {csv_path}")
        return {"FINISHED"}

    def bl_info(cls, text, lvl=None):
        lvl = "INFO" if not lvl else lvl
        cls.report({lvl}, f"{bl_info['name']}: {text}")


def get_path_button_txt(discipline):
    found = ""
    if model_paths[discipline]:
        found = "found"
    btn_txt = f"set {discipline.center(9-len(discipline))} model path {found}"
    return btn_txt


def deduplicate_paths(model_paths: dict):
    model_paths_count        = len(    model_paths.keys() )
    unique_model_paths_count = len(set(model_paths.keys()))
    duplicates_count = model_paths_count - unique_model_paths_count
    if not duplicates_count:
        return model_paths
    deduplicated = {}
    for k, v in model_paths.items():
        if v not in model_paths.values():
            deduplicated[k] = v
    return deduplicated


def find_models(path_str):
    root = Path(path_str)
    if not root.is_dir():
        root = root.parent
    for node in root.iterdir():
        if node.suffix != ".ifc":
            continue
        for name, regex in model_re.items():
            if re.findall(regex, node.name):
                model_paths[name] = node
                print(f"found: {name} {node.name} {regex}")


void_models = {"AU" : None}
arc_models  = {"A"  : None}
eng_models = {
    "BR" : None,
    "E"  : None,
    "H"  : None,
    "HKD": None,
    "L"  : None,
    "K"  : None,
    "S"  : None,
    "SP" : None,
}
models_dir  = {"DIR": None}

model_paths = {k:v for x in [void_models, arc_models, eng_models, models_dir]
               for k,v in x.items()}
model_re = {k:re.compile(f"_{k}_") for k, v in model_paths.items()}

csv_path = None
