"""Build the Windows exe with version info from src/__init__.py."""
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).parent

sys.path.insert(0, str(SRC))
from src import __version__  # noqa: E402

ver_parts = tuple(int(x) for x in __version__.split("."))
ver_tuple = ver_parts + (0,) * max(0, 4 - len(ver_parts))

VERSION_INFO = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={ver_tuple},
    prodvers={ver_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u''),
        StringStruct(u'FileDescription', u'RawPicker - Photo picking and cleaning tool'),
        StringStruct(u'FileVersion', u'{__version__}'),
        StringStruct(u'InternalName', u'RawPicker'),
        StringStruct(u'LegalCopyright', u''),
        StringStruct(u'OriginalFilename', u'RawPicker.exe'),
        StringStruct(u'ProductName', u'RawPicker'),
        StringStruct(u'ProductVersion', u'{__version__}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""

# Clean previous build artifacts
for p in ["dist", "build"]:
    shutil.rmtree(SRC / p, ignore_errors=True)
for p in SRC.glob("*.spec"):
    p.unlink(missing_ok=True)

# Write version info file
ver_file = SRC / "version_info.txt"
ver_file.write_text(VERSION_INFO, encoding="utf-8")

# Run PyInstaller
print(f"Building RawPicker v{__version__} ...")
subprocess.run(
    [sys.executable, "-m", "PyInstaller",
     "--onefile", "--windowed", "--strip",
     "--icon", str(SRC / "icon.ico"),
     "--version-file", str(ver_file),
     "--noconfirm",
     "--exclude-module", "setuptools",
     "--exclude-module", "pip",
     "--exclude-module", "distutils",
     "--exclude-module", "pkg_resources",
     "--name", "RawPicker",
     str(SRC / "src/main.py")],
    check=True,
)

# Clean up generated version file
ver_file.unlink(missing_ok=True)
print(f"Done: dist/RawPicker.exe (v{__version__})")
