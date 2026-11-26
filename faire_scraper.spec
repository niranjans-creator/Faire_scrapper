# PyInstaller build configuration for the Windows desktop application.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

project = Path(SPECPATH).parent
datas = [(str(project / "frontend"), "frontend")]
hiddenimports = collect_submodules("webview") + ["openpyxl"]

a = Analysis(
    [str(project / "build_desktop.py")],
    pathex=[str(project / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="FaireScraper", console=False)
