import bpy
from blenderbim.bim import import_ifc
import mathutils
import logging
import datetime
import collision
import bmesh
import numpy as np
import ifcclash
import os
from collections import namedtuple
from subprocess import Popen
from . import colors
from . import utils

# DONE identify voids
# DONE mark voids and pipes discipline / origin file
# DONE get bounding box corners
# DONE get void intersection pipes - delete the rest
# DONE check self-intersecting voids
# DONE only create the bboxes once in dict?
# DONE again transfer material info from wall to void
# DONE transfer pipe info (mat geo) to void
# DONE colorize different disciplines with different cols/mats str(rgba) as mat name
# DONE write csv with new voids data
# DONE create collections per disciplines (show/hide in blender with ctrl/shift click LMB)
# DONE try ifc import filter whitelist ifc classes
# DONE use void_bboxes key name not object pointer
# DONE implement target param name "source_param:->:target_param"
# DONE update csv export headers
# TODO prepare ifcs as blend: colorize
# TODO link blends to disc collections


def link_blend_ifc(model_path, discipline_name):
    blend_model_name = model_path.name + ".blend"
    blend_model_path = model_path.parent / blend_model_name
    if not blend_model_path.exists():
        return
    model_path = str(blend_model_path)
    with bpy.data.libraries.load(model_path, link=True) as (data_from, data_to):
        data_to.scenes = data_from.scenes
    for scene in bpy.data.scenes:
        if not scene.library or scene.library.filepath != model_path:
            continue
        for child in scene.collection.children:
            if "IfcProject" not in child.name:
                # print(f"skipped child IfcProject not in child.name: {child.name}")
                if len(child.children) == 0:
                    continue
                for sub_child in child.children:
                    if "IfcProject" in sub_child.name:
                        # print(f"but found in sub child: {child.children[0].name}")
                        bpy.data.scenes[0].collection.children[discipline_name].children.link(sub_child)
                continue
            bpy.data.scenes[0].collection.children[discipline_name].children.link(child)
    return True


def load_ifc(model_path, import_filter=None, selector=None):
    if import_filter and selector:
        print(import_filter, selector)
        filtered_import_ifc(model_path, import_filter, selector)
    else:
        bpy.ops.import_ifc.bim(filepath=str(model_path))


def filtered_import_ifc(ifc_file_path, import_filter, selector):
    ifc_import_settings = import_ifc.IfcImportSettings.factory(
        bpy.context,
        str(ifc_file_path),
        logging.getLogger('ImportIFC'),
    )
    if ".IfcSpace" in selector:
        ifc_import_settings.should_import_spaces = True
    ifc_import_settings.ifc_import_filter = import_filter
    ifc_import_settings.ifc_selector = selector
    ifc_importer = import_ifc.IfcImporter(ifc_import_settings)
    ifc_importer.execute()


def bbox_is_0_size(obj):
    bbox = get_bbox_from_object(obj)
    if sum(bbox.min) + sum(bbox.max) == 0.0:
        return True


def bboxes_overlap(bbx_a, bbx_b):
    directions = {"x": False, "y": False, "z": False}
    for direction in directions:
        a_max = getattr(bbx_a.max, direction)
        a_min = getattr(bbx_a.min, direction)
        b_max = getattr(bbx_b.max, direction)
        b_min = getattr(bbx_b.min, direction)
        # print(a_min, a_max, b_min, b_max)
        a_before_b = a_min <= b_min and a_max <= b_min
        if a_before_b:
            # print(direction, a_min, a_max, "before:", b_min, b_max)
            return False
        a_after_b  = a_min >= b_max and a_max >= b_max
        if a_after_b:
            # print(direction, a_min, a_max, "after:", b_max, b_min)
            return False
        # print(direction, before, after)
    # print("bboxes overlap!")
    return True


def bboxes_intersect(bbx_a, bbx_b):
    directions = {"x": False, "y": False, "z": False}
    for direction in directions:
        a_max = getattr(bbx_a.max, direction)
        a_min = getattr(bbx_a.min, direction)
        b_max = getattr(bbx_b.max, direction)
        b_min = getattr(bbx_b.min, direction)
        # print(a_min, a_max, b_min, b_max)
        a_before_b = a_min < b_min and a_max < b_min
        if a_before_b:
            # print(direction, a_min, a_max, "before:", b_min, b_max)
            return False
        a_after_b  = a_min > b_max and a_max > b_max
        if a_after_b:
            # print(direction, a_min, a_max, "after:", b_max, b_min)
            return False
        # print(direction, before, after)
    # print("bboxes overlap!")
    return True


def get_bbox_from_object(element):
    pts = [element.matrix_world @ mathutils.Vector(corner) for corner in element.bound_box]
    ## pts = [element.matrix_world @ v.co for v in element.data.vertices]
    # pts = [Pt(*tuple(corner)) for corner in element.bound_box]
    min_pt   = mathutils.Vector(min([tuple(pt) for pt in pts]))
    max_pt   = mathutils.Vector(max([tuple(pt) for pt in pts]))
    centroid = mathutils.Vector((
        (max_pt.x - min_pt.x) / 2 + min_pt.x,
        (max_pt.y - min_pt.y) / 2 + min_pt.y,
        (max_pt.z - min_pt.z) / 2 + min_pt.z,
    ))
    return Bbox(pts, min_pt, max_pt, centroid)


def is_elem_not_intersecting_any_void(elem, voids):
    elem_bbx = get_bbox_from_object(elem)
    for void in voids:
        # print(void, elem)
        if void == elem:
            continue
        void_bbx = void_bboxes[void.name]
        if void_bbx == elem_bbx:
            print(f"DUPLICATE!!: {void} - {elem}")
            continue
        intersects = bboxes_overlap(void_bbx, elem_bbx)
        if intersects:
            # print(f"should not delete elem: {elem}")
            # print(f"CX: {void} - {elem}")
            return False
    return True


def remove_duplicate_voids(pairs):
    looked_at   = set()
    delete_objs = set()
    for k, v in pairs.items():
        if v not in looked_at:
            delete_objs.add(k)
        looked_at.add(k)
    delete_objects(delete_objs)


def create_tri_proxy(elem, target_collection):
    elem_bbox = get_bbox_from_object(elem)
    offset = 0.03
    new_mesh = bpy.data.meshes.new("tri_void_proxy")
    vertices = [
        mathutils.Vector((
            elem_bbox.min.x -offset,
            elem_bbox.min.y -offset,
            elem_bbox.max.z,
        )),
        mathutils.Vector((
            elem_bbox.min.x -offset,
            elem_bbox.max.y +offset,
            elem_bbox.min.z,
        )),
        mathutils.Vector((
            elem_bbox.max.x +offset,
            elem_bbox.min.y -offset,
            elem_bbox.min.z,
        )),
        mathutils.Vector((
            elem_bbox.min.x -offset,
            elem_bbox.max.y +offset,
            elem_bbox.max.z,
        )),
        mathutils.Vector((
            elem_bbox.max.x +offset,
            elem_bbox.min.y -offset,
            elem_bbox.max.z,
        )),
        mathutils.Vector((
            elem_bbox.max.x +offset,
            elem_bbox.max.y +offset,
            elem_bbox.min.z,
        )),
    ]
    edges = []
    faces = [(0,1,2),(3,4,5)]
    new_mesh.from_pydata(vertices, edges, faces)
    new_mesh.update()
    elem_name_suffix = ""
    if len(elem.name.split(".")) > 1:
        elem_name_suffix = f".{elem.name.split('.')[-1]}"
    obj_name = f"tri_void_proxy{elem_name_suffix}"
    new_obj = bpy.data.objects.new(obj_name, new_mesh)
    target_collection.objects.link(new_obj)


def generate_void_proxies(voids):
    proxy_coll = bpy.data.collections.new("void_proxies")
    bpy.context.scene.collection.children["AU"].children.link(proxy_coll)
    for void in voids:
        create_tri_proxy(void, proxy_coll)


def create_void_tri_proxy_map(void_tri_proxies):
    proxy_tri_void_map = {}
    for proxy in void_tri_proxies:
        suffix = ""
        # print(proxy)
        if len(proxy.name.split(".")) > 1:
            suffix = f".{proxy.name.split('.')[-1]}"
        void_name = f"{PROV_VOID_ID}{suffix}"
        proxy_tri_void_map[proxy.name] = bpy.context.scene.objects.get(void_name)
    return proxy_tri_void_map


def add_to_cm(cm, object_names):
    for object_name in object_names:
        name = object_name.name
        obj = bpy.data.objects[name]
        # print(f"meshing for collision check: {object_name}")
        triangulated_mesh = triangulate_mesh(obj)
        mat = np.array(obj.matrix_world)
        mesh = ifcclash.Mesh()
        mesh.vertices = np.array([tuple(v.co) for v in triangulated_mesh.vertices])
        mesh.faces = np.array([tuple(p.vertices) for p in triangulated_mesh.polygons])
        cm.add_object(name, mesh, mat)


def get_collision_results(set_a=None, set_b=None):
    a_cm = collision.CollisionManager()
    b_cm = collision.CollisionManager()
    # no tri meshing needed for void_tri_proxies?
    add_to_cm(a_cm, set_a)
    add_to_cm(b_cm, set_b)
    return a_cm.in_collision_other(b_cm, return_data=True)


def triangulate_mesh(obj):
    mesh = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    del bm
    return mesh


def get_void_void_bbox_intersection_and_duplicates(voids):
    intersections = set()
    duplicates    = set()
    duplicate_pairs = {}
    void_bboxes = get_void_bboxes(voids)
    for void_a in voids:
        void_a_bbx = void_bboxes[void_a.name]
        for void_b in voids:
            void_b_bbx = void_bboxes[void_b.name]
            if void_a == void_b:  # skip self
                continue
            if void_a_bbx == void_b_bbx:
                print(f"DUPLICATE!!: {void_a} - {void_b}")
                duplicates.add(void_a)
                duplicates.add(void_b)
                duplicate_pairs[void_a] = void_b
                continue
            intersects = bboxes_overlap(void_a_bbx, void_b_bbx)
            if intersects:
                print(f"VOID-VOID-INTERSECTION!!: {void_a} - {void_b}")
                intersections.add(void_a)
                intersections.add(void_b)
    if intersections:
        print(f"WARNING: found {len(intersections)} void-void bbox intersections!")
    if duplicates:
        print(f"WARNING: found {len(duplicates)} void bbox duplicates!")
    return intersections, duplicates, duplicate_pairs


def get_void_bbox_overlap_objs(void, elems):
    overlapping = set()
    void_bbx = void_bboxes[void.name]
    for elem in elems:
        elem_bbx = get_bbox_from_object(elem)
        if bboxes_overlap(void_bbx, elem_bbx):
            overlapping.add(elem)
    return overlapping


def get_void_intersection_elem_data(void, discipline: str, elems,
                                    pset_keys=None, attrib_keys=None,
                                    map_materials=False, value_replace_map=None):
    void_bbx = void_bboxes[void.name]
    map_key_sep = ":->:"  # f"LongName:->:{discipline_name}_RoomLongNames"
    pset_keys   = pset_keys   if pset_keys   else ()
    attrib_keys = attrib_keys if attrib_keys else ()
    for elem in elems:
        elem_bbx = get_bbox_from_object(elem)
        overlaps = bboxes_overlap(void_bbx, elem_bbx)
        # print(void, elem)
        if not overlaps:
            continue
        # print("got overlap")
        for pset_name in pset_keys:
            elem_pset = elem.BIMObjectProperties.psets.get(pset_name)
            if not elem_pset:
                continue
            # print(f"found elem Model pset of {elem} for {void}")
            for key in pset_keys[pset_name]:
                target_key = key.replace('origin_', 'intersects_')
                if 'intersects_' not in target_key:
                    target_key = f"intersects_{target_key}"
                if map_key_sep in key:
                    target_key = f"intersects_{key.split(map_key_sep)[1]}"
                    key = key.split(map_key_sep)[0]
                # print(f"looking for {key} in {pset_name} to put value in: {target_key}")
                cx_key_val = elem_pset.properties.get(key)
                if not cx_key_val:
                    continue
                cx_key_val = cx_key_val.string_value
                if value_replace_map:
                    if value_replace_map.get(cx_key_val):
                        cx_key_val = value_replace_map[cx_key_val]
                # print(f"found {cx_key_val}\n")
                utils.add_custom_pset_key_value(
                    void,
                    "Pset_ProvisionForVoid",
                    target_key,
                    cx_key_val,
                    concat=True,
                )
        for attrib_name in attrib_keys:
            elem_attribs = elem.BIMObjectProperties.attributes
            if not elem_attribs:
                continue
            for key in attrib_keys[attrib_name]:
                target_key = f"intersects_{key}"
                if map_key_sep in key:
                    target_key = f"intersects_{key.split(map_key_sep)[1]}"
                    key = key.split(map_key_sep)[0]
                cx_key_val = elem_attribs.get(key)
                if not cx_key_val:
                    continue
                cx_key_val = cx_key_val.string_value
                utils.add_custom_pset_key_value(
                    void,
                    "Pset_ProvisionForVoid",
                    target_key,
                    cx_key_val,
                    concat=True,
                )
        if map_materials:
            mat_name = utils.get_elem_ifc_material_name(elem)
            if mat_name:
                utils.add_custom_pset_key_value(
                    void,
                    "Pset_ProvisionForVoid",
                    "intersects_WallMaterial",
                    mat_name,
                    concat=True,
                )


@utils.timing
def map_void_data_by_collision(set_a=None, set_b=None,
        pset_keys=None, attrib_keys=None, void_proxies=True,
        map_ifc_classes=False, map_materials=False, value_replace_map=None):
    if not all((set_a, set_b)):
        return
    err, results = get_collision_results(set_a=set_a, set_b=set_b)
    seen_pairs = set()
    map_key_sep = ":->:"  # f"LongName:->:{discipline_name}_RoomLongNames"
    for result in results:
        void_id = "tri_void_proxy." if void_proxies else PROV_VOID_ID
        result_pair = result.names
        result_names_str = str(result_pair)
        if result_names_str in seen_pairs:
            continue
        # print(35 * "-")
        # print(result_names_str)
        seen_pairs.add(str(result_pair))
        void  = [bpy.context.scene.objects.get(e) for e in result_pair if void_id in e]
        other = [bpy.context.scene.objects.get(e) for e in result_pair if void_id not in e]
        print(void, other)
        if not all((void, other)):
            print(f"no regular void/other pair: {result_pair}")
            continue
        void = next(iter(void))
        void = tri_proxy_void_map[void.name] if void_proxies else void
        other = next(iter(other))
        if not all((void, other)):
            print(f"no regular void/other pair: {result_pair}")
            continue
        if map_ifc_classes:
            if not getattr(other, "name"):
                print(f"elem name none: {other.name}")
            elif "/" not in  other.name:
                print(f"no / split found in elem name: {other.name}")
            else:
                other_ifc_class = other.name.split("/")[0]
                utils.add_custom_pset_key_value(
                    void,
                    "Pset_ProvisionForVoid",
                    "intersects_ifc_class",
                    other_ifc_class,
                    concat=True,
                )
        if pset_keys:
            for pset_name in pset_keys:
                elem_pset = other.BIMObjectProperties.psets.get(pset_name)
                if not elem_pset:
                    continue
                # print(f"found elem Model pset of {elem} for {void}")
                for key in pset_keys[pset_name]:
                    target_key = key.replace('origin_', 'intersects_')
                    if 'intersects_' not in target_key:
                        target_key = f"intersects_{target_key}"
                    # print(f"looking for {key} in {pset_name} to put value in: {target_key}")
                    if map_key_sep in key:
                        target_key = f"intersects_{key.split(map_key_sep)[1]}"
                        key = key.split(map_key_sep)[0]
                    cx_key_val = elem_pset.properties.get(key)
                    if not cx_key_val:
                        continue
                    cx_key_val = cx_key_val.string_value
                    if value_replace_map:
                        if value_replace_map.get(cx_key_val):
                            cx_key_val = value_replace_map[cx_key_val]
                    # print(f"found {cx_key_val}\n")
                    utils.add_custom_pset_key_value(
                        void,
                        "Pset_ProvisionForVoid",
                        target_key,
                        cx_key_val,
                        concat=True,
                    )
                    # print(void, cx_key_val)
        if attrib_keys:
            for attrib_name in attrib_keys:
                elem_attribs = other.BIMObjectProperties.attributes
                if not elem_attribs:
                    continue
                for key in attrib_keys[attrib_name]:
                    target_key = f"intersects_{key}"
                    if map_key_sep in key:
                        target_key = f"intersects_{key.split(map_key_sep)[1]}"
                        key = key.split(map_key_sep)[0]
                    cx_key_val = elem_attribs.get(key)
                    if not cx_key_val:
                        continue
                    cx_key_val = cx_key_val.string_value
                    utils.add_custom_pset_key_value(
                        void,
                        "Pset_ProvisionForVoid",
                        target_key,
                        cx_key_val,
                        concat=True,
                    )
        if map_materials:
            mat_name = utils.get_elem_ifc_material_name(other)
            if mat_name:
                utils.add_custom_pset_key_value(
                    void,
                    "Pset_ProvisionForVoid",
                    "intersects_WallMaterial",
                    mat_name,
                    concat=True,
                )


@utils.timing
def delete_objects(delete_objs):
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.object.delete({"selected_objects": delete_objs})
    print(f"deleted {len(delete_objs)} objects")


def sort_voids_other(elements):
    voids, other = [], []
    for elem in elements:
        if "ProvisionForVoid" in elem.name:
            voids.append(elem)
        else:
            other.append(elem)
    print(f"found {len(voids)} voids elements")
    print(f"found {len(other)} other elements")
    return voids, other


def find_non_void_intersecting_elems(elements, voids):
    objs_to_delete = []
    # intersecting = {False: 0, True: 0}
    for elem in elements:
        not_intersecting = is_elem_not_intersecting_any_void(elem, voids)
        if not not_intersecting:
            # print(f"keep: {elem}")
            # intersecting[True] += 1
            continue
        else:
            objs_to_delete.append(elem)
            # intersecting[False] += 1
    # print(f"ratio of intersecting elements: {intersecting}")
    return objs_to_delete


def find_void_intersecting_elems(elements, voids):
    intersecting = []
    for elem in elements:
        not_intersecting = is_elem_not_intersecting_any_void(elem, voids)
        if not not_intersecting:
            intersecting.append(elem)
    return intersecting


@utils.timing
def get_void_bboxes(voids):
    void_bbox_map = {}
    for void in voids:
        void_bbox_map[void.name] = get_bbox_from_object(void)
    return void_bbox_map


def write_void_data_to_csv(csv_path):
    voids = utils.get_elems_by_name("ProvisionForVoid")
    with open(csv_path, "w") as csv_txt:
        header = [
            'ifc_guid', 'ifc_desc', 'name', 'storey',
            'Shape', 'Diameter',
            'Depth', 'Width', 'Height',
            'Brandschott_ID',
            'Ausfuehrungsstatus',
            'Plancal_Gewerke',
            'Plancal_Abbreviation',
            'intersects_discipline',
            'intersects_model',
            'intersects_ifc_class',
            'intersects_Pipe_Material',
            'intersects_Pipe_Querschnitt_Breite',
            'intersects_Pipe_Querschnitt_Hoehe',
            'intersects_Pipe_Durchmesser',
            'intersects_Pipe_Guids',
            'intersects_Pipe_Names',
            'intersects_Pipe_Infos',
            'intersects_Pipe_Medium',
            'intersects_BR_FireRating',
            'intersects_WallName',
            'intersects_WallMaterial',
            'intersects_A_RoomGuids',
            'intersects_A_RoomNames',
            'intersects_A_RoomLongNames',
            # 'intersects_A_FireRating',
            # 'intersects_A_Mehrschichtiger Aufbau Typ',
        ]
        csv_txt.write(";".join(header) + "\n")
        for void in voids:
            void_data = {e: "" for e in header}
            bim_obj_props = getattr(void, 'BIMObjectProperties')
            pl = [dict(prp.items()) for prp in bim_obj_props['attributes']]
            ifc_guid = bim_obj_props.attributes["GlobalId"].string_value
            ifc_desc = bim_obj_props.attributes["Description"].string_value
            void_data["ifc_guid"] = ifc_guid
            void_data["ifc_desc"] = ifc_desc
            void_data["name"] = void.name
            void_data["storey"] = utils.get_elem_storey(void)
            # ifc_guid = bim_obj_props["attributes"][0].items()[-1][-1]
            # ifc_guid = [d for d in pl if d.get("name") == "GlobalId"]
            # ifc_desc = [d for d in pl if d.get("name") == "Description"]
            # ifc_desc = ifc_desc[0]["string_value"]
            pset_prov_void = void.BIMObjectProperties.psets['Pset_ProvisionForVoid']
            prov_data = {k: v.string_value for k, v in pset_prov_void.properties.items()}
            void_data.update(prov_data)
            line_data = ";".join(void_data.values())
            csv_txt.write(line_data + "\n")
    print(f"{len(voids)} void data entries exported to:\n{csv_path}")


@utils.timing
def colorize_elements(elems=None, color=None):
    if not color:
        color = (0.25, 0.5, 1, 1)  # rgba
    if not elems:
        elems = bpy.context.selected_objects
    bpy.ops.object.select_all(action='DESELECT')
    elem_count = len(elems)
    rgba_mat = get_or_create_rgba_mat(color)
    for elem in elems:
        # print(elem.name)
        # remove color
        if elem.data:
            elem.data.materials.clear()
            # colorize elem
            elem.data.materials.append(rgba_mat)
        else:
            print(f"no elem.data at object: {elem}")
    print(f"colorized {elem_count} elements")


def get_or_create_rgba_mat(color: tuple):
    rgba_str = str(color).replace(" ","_")
    rgba_mat = bpy.data.materials.get(rgba_str)
    if not rgba_mat:
        rgba_mat = bpy.data.materials.new(name=rgba_str)
        rgba_mat.diffuse_color = color
    return rgba_mat


@utils.timing
def merge_plancal_data(objs):
    for obj in objs:
        gewerke = set()
        pcp = obj.BIMObjectProperties.psets.get("Pset Plancal nova - Enerconom")
        if not pcp:
            continue
        abbrev = ""
        gewerke_str = ""
        prop = pcp.properties.get("Abbreviation")
        if prop:
            abbrev = prop.string_value
        for num in range(1,9):
            prop = pcp.properties.get(f"Gewerk {num}")
            if prop:
                # print(prop.string_value)
                if prop.string_value:
                    gewerke.add(prop.string_value)
            else:
                break
        if gewerke:
            gewerke_str = ",".join(sorted(gewerke))
        # print(obj.name, ",".join(sorted(gewerke)))
        if gewerke_str:
            utils.add_custom_pset_key_value(obj, "Pset_ProvisionForVoid", "Plancal_Gewerke", gewerke_str)
        if abbrev:
            utils.add_custom_pset_key_value(obj, "Pset_ProvisionForVoid", "Plancal_Abbreviation", abbrev)


@utils.timing
def get_voids_and_discipline_elems(discipline_model_name):
    bpy.ops.object.select_all(action='DESELECT')
    voids = utils.get_elems_by_name("IfcBuildingElementProxy/ProvisionForVoid")
    discipline_elems = utils.get_elems_by_param_values(
        discipline_model_name,
        only_key="origin_model",
    )
    discipline_elems = [obj for obj in discipline_elems if getattr(obj, "type") == "MESH"]
    return voids, discipline_elems


@utils.timing
def add_elems_to_collection(elems, col_name):
    collection = bpy.context.scene.collection.children.get(col_name)
    if collection:
        for elem in elems:
            _ = collection.objects.link(elem)


def create_collections(names):
    for name in names:
        if name == "DIR":
            continue
        bpy.ops.collection.create(name=name)
        bpy.context.scene.collection.children.link(bpy.data.collections[name])


def move_link_to_collection(discipline_name):
    ifc_prj_coll = next(iter([coll for coll in bpy.data.collections if "IfcProject" in coll.name]))
    bpy.context.scene.collection.children[discipline_name].children.link(ifc_prj_coll)
    bpy.context.scene.collection.children.unlink(ifc_prj_coll)


def unlink_ifc_collections():
    ifc_collections = [coll for coll in bpy.data.collections if "IfcProject" in coll.name]
    for ifc_collection in ifc_collections:
        bpy.context.scene.collection.children.unlink(ifc_collection)


def blend_ifc_exists(ifc_model_path):
    blend_model_name = ifc_model_path.name + ".blend"
    blend_model_path = ifc_model_path.parent / blend_model_name
    if blend_model_path.exists():
        print(f"{blend_model_name} model found")
        return blend_model_path
    else:
        print(f"{blend_model_name} model not found!")


@utils.timing
def cache_ifc_in_blend_model(model_paths):
    script_path = r"C:\Users\frederic.beaupere\repos\ifc_void_data\blend_ifc_cache.py"
    for discipline_name, model_path in model_paths.items():
        if discipline_name == "DIR":
            continue
        if blend_ifc_exists(model_path):
            print(f"{discipline_name:4}: does already have a blend ifc model")
            continue
        blend_model_name = model_path.name + ".blend"
        blend_model_path = model_path.parent / blend_model_name
        os.environ["ivd_model_path"] = str(blend_model_path)
        os.environ["ivd_model_disc"] = discipline_name
        print(f"path from cache func: {discipline_name:4}: {model_path}")
        cmd = [str(bpy.app.binary_path), "--python", script_path]
        # cmd = [str(bpy.app.binary_path), "--python", script_path]
        print(f"running: {cmd}")
        #ret = os.popen(" ".join(cmd)).read()
        #print(ret)
        Popen(
            cmd,
            env={
                "ivd_model_path":str(blend_model_path),
                "ivd_model_disc":discipline_name,
            },
        ).wait()
    """
    if blend_ifc_exists(model_path):
        print(f"{discipline_name:4}: does not have a blend ifc model")
        return
    bpy.ops.wm.read_homefile(app_template="")
    create_collections([discipline_name])
    load_ifc(
        model_path,
        import_filter=IFC_SELECTORS[discipline_name]["filter"  ],
        selector=IFC_SELECTORS[     discipline_name]["selector"],
    )
    utils.tag_new_elements_with_model_name(discipline_name, model_path.name)
    voids, discipline_elems = get_voids_and_discipline_elems(model_path.name)
    #if discipline_name != "BR":
    #    colorize_elements(elems=discipline_elems, color=colors.COL_MAP[discipline_name])
    add_elems_to_collection(discipline_elems, discipline_name)
    """


@utils.timing
def process_voids(discipline_name, model_path):
    global void_proxies
    global tri_proxy_void_map
    load_ifc(
        model_path,
        import_filter=IFC_SELECTORS[discipline_name]["filter"  ],
        selector=IFC_SELECTORS[     discipline_name]["selector"],
    )
    move_link_to_collection(discipline_name)
    utils.tag_new_elements_with_model_name(discipline_name, model_path.name)
    voids = utils.get_elems_by_name("ProvisionForVoid")
    colorize_elements(elems=voids, color=colors.COL_MAP[discipline_name])
    # add_elems_to_collection(voids, discipline_name)
    cx, dups, pairs = get_void_void_bbox_intersection_and_duplicates(voids)
    remove_duplicate_voids(pairs)
    voids = [elem for elem in bpy.context.scene.objects if PROV_VOID_ID in elem.name]
    generate_void_proxies(voids)
    merge_plancal_data(voids)
    bpy.ops.object.select_all(action='DESELECT')
    void_proxies = utils.get_elems_by_name("tri_void_proxy")
    utils.tag_new_elements_with_model_name("PRX", "tri_void_proxy_generated")
    colorize_elements(elems=void_proxies, color=colors.COL_MAP["PRX"])
    # void_proxies = [elem for elem in bpy.context.scene.objects if "tri_void_proxy" in elem.name]
    tri_proxy_void_map = create_void_tri_proxy_map(void_proxies)
    bpy.ops.object.select_all(action='DESELECT')
    print(f"model name: {model_path.name}")
    return get_void_bboxes(voids)


@utils.timing
def process_eng_ifc(discipline_name, model_path, delete_non_colliding=False):
    print(f"\nprocess_eng_ifc {discipline_name} start")
    linked_blend_model = link_blend_ifc(model_path, discipline_name)
    if not linked_blend_model:
        load_ifc(
            model_path,
            import_filter=IFC_SELECTORS[discipline_name]["filter"  ],
            selector=IFC_SELECTORS[     discipline_name]["selector"],
        )
        utils.tag_new_elements_with_model_name(discipline_name, model_path.name)
    if delete_non_colliding:
        voids, discipline_elems = get_voids_and_discipline_elems(model_path.name)
        objs_to_delete = find_non_void_intersecting_elems(
            elements=discipline_elems,
            voids=voids,
        )
        delete_objects(objs_to_delete)
    voids, discipline_elems = get_voids_and_discipline_elems(model_path.name)
    print(f"got {len(discipline_elems)} discipline_elems")
    if not linked_blend_model:
        if discipline_name != "BR":
            colorize_elements(elems=discipline_elems, color=colors.COL_MAP[discipline_name])
        # move_link_to_collection(discipline_name)
        add_elems_to_collection(discipline_elems, discipline_name)
    print(f"still got {len(discipline_elems)} discipline_elems")
    map_void_data_by_collision(
        set_a=void_proxies,
        set_b=discipline_elems,
        void_proxies=True,
        map_ifc_classes=True,
        attrib_keys={
            "attributes": [
                "GlobalId:->:Pipe_Guids",
            ],
        },
        pset_keys={
            "FRM": [
                "FRM_FireRating:->:BR_FireRating",
            ],
            "Model": [
                "origin_model",
                "origin_discipline"
            ],
            "Pset Plancal nova - Enerconom": [
                "A (mm):->:Pipe_Querschnitt_Breite",
                "B (mm):->:Pipe_Querschnitt_Hoehe",
                "D1 (mm):->:Pipe_Durchmesser",
                "D1:->:Pipe_Durchmesser",
                "Material:->:Pipe_Material",
                "Medium:->:Pipe_Medium",
                "Name:->:Pipe_Names",
                "Info:->:Pipe_Infos",
                "Info 2:->:Pipe_Infos",
            ],
        },
        value_replace_map=utils.PIPE_MAT_MAP,
    )
    bpy.ops.object.select_all(action='DESELECT')
    print(f"model name: {model_path.name}")
    return voids


@utils.timing
def process_arc_ifc(discipline_name, model_path):
    print(f"\nprocess_arc_ifc {discipline_name} start")
    global void_bboxes
    linked_blend_model = link_blend_ifc(model_path, discipline_name)
    if not linked_blend_model:
        load_ifc(
            model_path,
            import_filter=IFC_SELECTORS[discipline_name]["filter"],
            selector=IFC_SELECTORS[     discipline_name]["selector"],
        )
        utils.tag_new_elements_with_model_name(discipline_name, model_path.name)
    voids, discipline_elems = get_voids_and_discipline_elems(model_path.name)
    print(f"got {len(discipline_elems)} discipline_elems")
    void_bboxes = get_void_bboxes(voids)
    if not linked_blend_model:
        # move_link_to_collection(discipline_name)
        add_elems_to_collection(discipline_elems, discipline_name)
    walls = [elem for elem in discipline_elems if elem.name.startswith("IfcWall")]
    print(f"got {len(walls)} walls")
    map_void_data_by_collision(
        set_a=void_proxies,
        set_b=walls,
        void_proxies=True,
        attrib_keys = {
            "attributes": [
                "Name:->:WallName",
            ],
        },
        pset_keys={
            # "Bauteilbenennung": ["Mehrschichtiger Aufbau Typ"],
            # "Pset_WallCommon"  : ["FireRating"],
        },
        map_materials=True,
    )
    spaces = [elem for elem in discipline_elems if elem.name.startswith("IfcSpace")]
    print(f"got {len(spaces)} spaces")
    map_void_data_by_collision(
        set_a=void_proxies,
        set_b=spaces,
        void_proxies=True,
        attrib_keys = {
            "attributes": [
                f"GlobalId:->:{discipline_name}_RoomGuids",
                f"Name:->:{discipline_name}_RoomNames",
                f"LongName:->:{discipline_name}_RoomLongNames",
            ],
        },
    )
    print(f"model name: {model_path.name}")


@utils.timing
def process_ifc_models(model_paths: dict, eng_models_paths):
    print("process_ifc_models start")
    global void_bboxes

    #cache_ifc_in_blend_model(model_paths)
    #return

    create_collections(model_paths)

    void_bboxes = process_voids("AU", model_paths["AU"])

    print(eng_models_paths)
    for name, path in eng_models_paths.items():
        process_eng_ifc(name, path)

    if model_paths.get("A"):
        process_arc_ifc("A", model_paths["A"])

    # unlink_ifc_collections()
    utils.set_3dview_to_all()
    utils.toggle_expand(2)

    today_iso_short = str(datetime.datetime.now().date()).replace("-", "")
    ifc_void_root  = model_paths["AU"].parent
    csv_void_table = ifc_void_root / f"{today_iso_short}_voids.csv"
    write_void_data_to_csv(csv_void_table)


void_bboxes = {}
void_proxies = []
tri_proxy_void_map = {}

Bbox = namedtuple("Bbox", "pts min max centroid")
PROV_VOID_ID = "IfcBuildingElementProxy/ProvisionForVoid"

IFC_FLOW_SEGMENTS = {
    "filter"  : "WHITELIST",
    "selector": '.IfcFlowSegment',
}
IFC_FLOW = {
    "filter"  : "WHITELIST",
    "selector": '.IfcFlowSegment | '
                '.IfcFlowTerminal | '
                '.IfcFlowTreatmentDevice | '
                '.IfcFlowController | '
                '.IfcFlowFitting'
}
IFC_FLOWSEGFIT = {
    "filter"  : "WHITELIST",
    "selector": '.IfcFlowSegment | '
                '.IfcFlowFitting'
}
IFC_FLOWSEGFITDIST = {
    "filter"  : "WHITELIST",
    "selector": '.IfcFlowSegment | '
                '.IfcDistributionElement | '
                '.IfcFlowFitting'
}
IFC_NO_VOIDS = {
    "filter"  : "BLACKLIST",
    "selector": '.IfcBuildingElementProxy[Name*="ProvisionForVoid"]',
}
IFC_VOIDS = {
    "filter"  : "WHITELIST",
    "selector": '.IfcBuildingElementProxy[Name*="ProvisionForVoid"]',
}
IFC_PROXY_ELEMS = {
    "filter"  : "WHITELIST",
    "selector": '.IfcBuildingElementProxy',
}
IFC_WALLS_SLABS_SPACES = {
    "filter"  : "WHITELIST",
    "selector": '.IfcWall | .IfcSlab | .IfcSpace',
}

IFC_SELECTORS = {
    "A"  : IFC_WALLS_SLABS_SPACES,
    "AU" : IFC_VOIDS,
    "BR" : IFC_PROXY_ELEMS,
    "E"  : IFC_FLOWSEGFITDIST,
    "H"  : IFC_FLOWSEGFIT,
    "HKD": IFC_FLOWSEGFIT,
    "L"  : IFC_FLOW,
    "K"  : IFC_FLOW_SEGMENTS,
    "S"  : IFC_FLOWSEGFIT,
    "SP" : IFC_FLOW_SEGMENTS,
}
