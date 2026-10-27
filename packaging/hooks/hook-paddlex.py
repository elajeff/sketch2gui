from importlib.metadata import PackageNotFoundError

from PyInstaller.utils.hooks import copy_metadata
from paddlex.utils import deps

required = set(deps.BASE_DEP_SPECS)
for extra in ("ocr", "ocr-core"):
    required.update(deps.EXTRAS.get(extra, {}))
required.update(("paddlex", "paddleocr", "paddlepaddle"))

datas = []
for package in sorted(required):
    try:
        datas.extend(copy_metadata(package))
    except PackageNotFoundError:
        continue
