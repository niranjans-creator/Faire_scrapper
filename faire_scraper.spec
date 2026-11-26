# PyInstaller build configuration for the Windows desktop application.
from pathlib import Path

project = Path(SPECPATH).parent
datas = [(str(project / "frontend"), "frontend")]

a = Analysis(
    [str(project / "src" / "faire_scraper" / "desktop.py")],
    pathex=[str(project / "src")],
    datas=datas,
    hiddenimports=["webview", "openpyxl"],
    excludes=[],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="FaireScraper", console=False)
