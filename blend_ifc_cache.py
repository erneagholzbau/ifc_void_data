import bpy
from pathlib import Path
import os
import time





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

time.sleep(2)
print("hello from blend ifc cache!")

#if os.environ.get("ivd_model_path"):
print(os.environ["ivd_model_path"])  # of target blend file
print(os.environ["ivd_model_disc"])

discipline_name = os.environ["ivd_model_disc"]
blend_model_path = Path(os.environ["ivd_model_path"])
ifc_model_name = blend_model_path.name.rsplit(".blend")[0]
ifc_model_path = blend_model_path.parent / ifc_model_name

load_ifc(
    ifc_model_path,
    import_filter=IFC_SELECTORS[discipline_name]["filter"],
    selector=IFC_SELECTORS[discipline_name]["selector"],
)
# bpy.ops.wm.save_as_mainfile(os.environ["ivd_model_path"])





