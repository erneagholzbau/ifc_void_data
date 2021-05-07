from pathlib import Path
import shutil
import zipfile


with open("__init__.py") as init:
    content = init.readlines()
source = ""
for i, line in enumerate(content):
    if i > 13:
        break
    source += line
exec(source)

tag     = bl_info["tag"]
version = bl_info["version"]

ROOT_DIR = Path(__file__).parent
USER = ROOT_DIR.parent.parent
ADDON = USER / "AppData" / "Roaming" / "Blender Foundation" / "Blender" / "2.91" / "scripts" / "addons" / tag
target_zip = ROOT_DIR / "dist" / f"{version}_{tag}.zip"
file_paths = {
    Path(p).absolute() for p in ROOT_DIR.iterdir()\
    if p.name.endswith(".py")\
    if p.name.endswith(".md")\
    if p.name.endswith("LICENSE")
}

for file_path in file_paths:
    shutil.copy(file_path, ADDON / file_path.name)

with zipfile.ZipFile(target_zip, 'w') as zip_file:
    for file_path in file_paths:
        zip_file.write(file_path, arcname=f"{tag}/{file_path.name}")

