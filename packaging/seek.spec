# PyInstaller 打包配置：pyinstaller packaging/seek.spec
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent
datas = [(str(ROOT / "app" / "static"), "app/static")]
binaries = []
hiddenimports = collect_submodules("uvicorn") + collect_submodules("app")

# Chroma 大量使用动态导入，并依赖 Rust 原生模块、onnxruntime 与 tokenizers（本地小模型）
for pkg in ("chromadb", "chromadb_rust_bindings", "onnxruntime", "tokenizers"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

icon = None
if sys.platform == "darwin" and (ROOT / "packaging" / "seek.icns").exists():
    icon = str(ROOT / "packaging" / "seek.icns")
elif sys.platform == "win32" and (ROOT / "packaging" / "seek.ico").exists():
    icon = str(ROOT / "packaging" / "seek.ico")

a = Analysis(
    [str(ROOT / "desktop.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "torch", "sentence_transformers", "pytest", "IPython", "pandas", "PIL", "lxml"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Seek",
    console=False,  # 窗口程序，不弹出命令行
    icon=icon,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Seek")

if sys.platform == "win32":
    import shutil

    # .NET 只读取与 exe 同目录、同名的 .config 文件
    shutil.copy(ROOT / "packaging" / "Seek.exe.config", Path(DISTPATH) / "Seek" / "Seek.exe.config")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Seek.app",
        icon=icon,
        bundle_identifier="app.seek.desktop",
        info_plist={
            "CFBundleDisplayName": "Seek",
            "CFBundleShortVersionString": "0.2.1",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
