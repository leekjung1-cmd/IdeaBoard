"""exe로 묶기: python build_release.py
→ D:\AI Dev\IdeaBoard-release\IdeaBoard-<버전>.zip (다른 PC에 풀어서 IdeaBoard.exe 실행)"""
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

from version import VERSION

SRC = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(SRC), "IdeaBoard-release")
WORK = os.path.join(tempfile.gettempdir(), "IdeaBoard-build")

# 이 프로그램이 안 쓰는 Qt 부품 (Qt6Qml.dll은 QtCore가 필요로 해서 남겨야 함)
TRIM_FILES = ["opengl32sw.dll", "Qt6Quick.dll", "Qt6QmlModels.dll", "Qt6VirtualKeyboard.dll",
              "plugins/platforms/qdirect2d.dll", "plugins/platforms/qminimal.dll",
              "plugins/platforms/qoffscreen.dll"]
TRIM_DIRS = ["plugins/platforminputcontexts", "plugins/tls", "plugins/networkinformation"]
KEEP_TRANSLATIONS = {"qtbase_ko.qm"}


def version_file():
    """exe 속성(자세히)에 보이는 버전 정보."""
    nums = tuple(int(x) for x in VERSION.split(".")) + (0,)
    path = os.path.join(WORK, "version_info.txt")
    os.makedirs(WORK, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(VERSION_INFO % {"t": repr(nums[:4]), "v": VERSION})
    return path


VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(t)s, prodvers=%(t)s),
  kids=[StringFileInfo([StringTable('041204B0', [
    StringStruct('FileDescription', 'Idea Board'),
    StringStruct('ProductName', 'Idea Board'),
    StringStruct('FileVersion', '%(v)s'),
    StringStruct('ProductVersion', '%(v)s')])]),
    VarFileInfo([VarStruct('Translation', [0x0412, 1200])])]
)
"""


def main():
    dist = os.path.join(WORK, "dist")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", os.path.join(SRC, "main.pyw"),
        "--name", "IdeaBoard", "--windowed", "--noconfirm", "--clean",
        "--icon", os.path.join(SRC, "app.ico"),
        "--exclude-module", "tkinter",
        "--version-file", version_file(),
        "--distpath", dist, "--workpath", os.path.join(WORK, "build"), "--specpath", WORK,
    ], check=True)

    app = os.path.join(dist, "IdeaBoard")
    qt = os.path.join(app, "_internal", "PySide6")
    for f in TRIM_FILES:
        p = os.path.join(qt, f)
        if os.path.exists(p):
            os.remove(p)
    for d in TRIM_DIRS:
        shutil.rmtree(os.path.join(qt, d), ignore_errors=True)
    tr = os.path.join(qt, "translations")
    for f in os.listdir(tr):
        if f not in KEEP_TRANSLATIONS:
            p = os.path.join(tr, f)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    shutil.copy2(os.path.join(SRC, "읽어주세요.txt"), app)

    os.makedirs(OUT_DIR, exist_ok=True)
    zip_path = os.path.join(OUT_DIR, "IdeaBoard-%s.zip" % VERSION)
    tmp = zip_path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, _, files in os.walk(app):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, dist).replace("\\", "/"))
    os.replace(tmp, zip_path)
    print(f"완료: {zip_path} ({os.path.getsize(zip_path) / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
