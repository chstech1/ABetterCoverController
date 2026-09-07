"""Build a clean install archive without development files or bytecode."""

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parents[1]
component = root / "custom_components" / "better_cover"
version = json.loads((component / "manifest.json").read_text())["version"]
output = root / "dist" / f"better-cover-{version}.zip"
output.parent.mkdir(exist_ok=True)
with ZipFile(output, "w", ZIP_DEFLATED) as archive:
    for path in sorted(component.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix in (".py", ".json", ".png"):
            archive.write(path, path.relative_to(root))
    archive.write(root / "README.md", "README.md")
    archive.write(root / "LICENSE", "LICENSE")
print(output)
