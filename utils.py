import bpy
import datetime
import re


def timing(function):
    def wrap(*args, **kwargs):
        start_time = datetime.datetime.now()
        result = function(*args, **kwargs)
        end_time = datetime.datetime.now()
        duration = end_time - start_time
        f_name = function.__name__
        print(f"{f_name} took {duration}")
        return result
    return wrap


def add_custom_pset_key_value(elem, name_pset, key, value, concat=False):
    pset = elem.BIMObjectProperties.psets.get(name_pset)
    if not pset:
        pset = elem.BIMObjectProperties.psets.add()
    pset.name = name_pset
    prop = pset.properties.get(key)
    if not prop:
        prop = pset.properties.add()
        prop.name = key
        prop.string_value = value
    else:  # property existed already -> concatenate/overwrite
        if concat:
            existing = prop.string_value
            if value not in existing:
                prop.string_value = f"{existing}, {value}"
        else:  # overwrite
            prop.string_value = value



def tag_new_elements_with_model_name(discipline_name, model_name):
    for elem in bpy.data.objects:
        if not elem.BIMObjectProperties.psets.get("Model"):
            # print(discipline_name, model_name)
            add_custom_pset_key_value(
                elem,
                "Model",
                "origin_model",
                model_name,
            )
            add_custom_pset_key_value(
                elem,
                "Model",
                "origin_discipline",
                discipline_name,
            )


def get_dict_key_from_value(search_dict, value):
    for key, val in search_dict.items():
        if val == value:
            return key
    print(f"value: {val} does not exist")


def select_by_name(name_part):
    bpy.ops.object.select_all(action='DESELECT')
    _ = [e.select_set(True) for e in bpy.data.objects if name_part in e.name]
    selected_objects = bpy.context.selected_objects
    # print(f"selected: {len(selected_objects)} objects")
    return selected_objects


def set_3dview_to_all():
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            ctx = bpy.context.copy()
            ctx['area'] = area
            ctx['region'] = area.regions[-1]
            bpy.ops.view3d.view_all(ctx)


def toggle_expand(state):
    area = next(a for a in bpy.context.screen.areas if a.type == 'OUTLINER')
    bpy.ops.outliner.show_hierarchy({'area': area}, 'INVOKE_DEFAULT')
    for i in range(state):
        bpy.ops.outliner.expanded_toggle({'area': area})
    area.tag_redraw()


def get_elems_by_name(name_part):
    elems = []
    for elem in bpy.data.objects:
        if name_part in elem.name:
            elems.append(elem)
    bpy.ops.object.select_all(action='DESELECT')
    return elems


def cull_ifc_logic_objects(objs):
    culled = []
    re_ifc_logic_objs = {
        re.compile("IfcSite/"),
        re.compile("IfcBuildingStorey/"),
        re.compile("IfcSite/"),
        re.compile("IfcProject/"),
        re.compile("Ifc.+Type/"),
    }
    for obj in objs:
        logic_obj = False
        for regex in re_ifc_logic_objs:
            if re.match(regex, obj.name):
                logic_obj = True
                break
        if not logic_obj:
            culled.append(obj)
    return culled


def select_elems_by_param_values(value_part, only_key=None):
    vals_obj = set()
    for elem in bpy.data.objects:
        for pset_name in elem.BIMObjectProperties.psets.keys():
            #print(f"_____________\n{pset_name}")
            elem_model_pset = elem.BIMObjectProperties.psets[pset_name]
            for key, val in elem_model_pset.properties.items():
                #print(f"  {key:29} :: {val.string_value}")
                if only_key:
                    if key != only_key:
                        continue
                if value_part in val.string_value:
                    vals_obj.add(elem)
    select_results = [e.select_set(True) for e in vals_obj]
    selected_objects = bpy.context.selected_objects
    print(f"selected: {len(select_results)} objects")
    return selected_objects


def get_elems_by_param_values(value_part, only_key=None):
    vals_obj = set()
    for elem in bpy.data.objects:
        for pset_name in elem.BIMObjectProperties.psets.keys():
            #print(f"_____________\n{pset_name}")
            elem_model_pset = elem.BIMObjectProperties.psets[pset_name]
            for key, val in elem_model_pset.properties.items():
                #print(f"  {key:29} :: {val.string_value}")
                if only_key:
                    if key != only_key:
                        continue
                if value_part in val.string_value:
                    vals_obj.add(elem)
    return vals_obj


def get_elem_storey(elem):
    users_collections = elem.users_collection
    obj_storey = [coll for coll in users_collections if "IfcBuildingStorey" in coll.name]
    if obj_storey:
        return obj_storey[0].name


def get_elem_material_name(elem):
    mats = get_elem_materials(elem)
    mat_name = ""
    for mat in mats:
        if not mat.name:
            continue
        mat_name = mat.name
        for search, result in MAT_MAP.items():
            if search in mat_name:
                return result
    return mat_name


def get_elem_materials(elem):
    materials = []
    for mat in elem.data.materials:
        # print(mat.name)
        materials.append(mat)
    return materials


def get_elem_ifc_material_name(elem):
    mats = get_elem_ifc_materials(elem)
    mats_set = set()
    for mat in mats:
        mats_set.add(mat.name)
    unique_mat_count = len(mats_set)
    if unique_mat_count == 1:
        single_mat = mats_set.pop()
        for search, result in MAT_MAP.items():
            if search in single_mat:
                return result
    elif unique_mat_count > 1:
        mat_name = get_mat_name_from_material_combinations(mats_set)
        if mat_name:
            return mat_name
    elif unique_mat_count == 0:
        return ""
    return str(mats_set)


def get_elem_ifc_materials(elem):
    materials = []
    if elem.BIMObjectProperties.material_type == "IfcMaterial":
        # items of set are empty?
        return materials
    mat_components = []
    if elem.BIMObjectProperties.material_type == "IfcMaterialLayerSet":
        mat_components = elem.BIMObjectProperties.material_set["material_layers"]
    elif elem.BIMObjectProperties.material_type == "IfcMaterialConstituentSet":
        mat_components = elem.BIMObjectProperties.material_set["material_constituents"]
    for mat_component in mat_components:
        for k, v in mat_component.items():
            # print(k, v)
            if k == "material":
                materials.append(v)
    return materials


def get_mat_name_from_material_combinations(mat_name_set):
    for name, combinations_list in MAT_COMBO_MAP.items():
        # print("-"*55)
        # print(f"looking at combination: {combination}")
        found = {k:None for k in mat_name_set}
        for combination in combinations_list:
            for word in combination:
                for item in mat_name_set:
                    # print(f"searching for {word} in {item}")
                    if word in item:
                        # print(f"found: {word}")
                        found[item] = True
                        if all(found.values()):
                            # print(f"found all!! it is: {name}")
                            return name


MAT_MAP = {
    "ipskartonplatte": "GK",
    "eton"           : "Beton",
    "alksandstein"   : "KS",
    "ämmung"         : "Daemmung",
    "Glas"           : "Glas",
    "Holzlattung"    : "Holzlattung",
}

MAT_COMBO_MAP = {
    "GK": [
        {"Gipskarton","Dämmung Mineralwolle"},
        {"Gipskarton","Dämmung"             },
        {"Gipskarton","Mineralwolle"        },
    ],
}

PIPE_MAT_MAP = {
    "Rohr DIN EN ISO 1127"   : "Edelstahl",
    "Stahlrohr nach DIN 2448": "Stahl",
}
