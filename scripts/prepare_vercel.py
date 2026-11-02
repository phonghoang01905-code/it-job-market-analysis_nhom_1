"""Stage only dashboard source and public CSV, never local config or CV uploads."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def prepare(target: Path | None = None) -> Path:
    destination = target or ROOT / ".tools" / "vercel-stage"
    destination.mkdir(parents=True, exist_ok=True)
    config = ROOT / "deploy" / "vercel"
    for name in ["app.py", "dashboard_entry.py", "requirements.txt", "vercel.json", ".python-version", ".vercelignore"]:
        shutil.copy2(config / name, destination / name)
    shutil.copy2(ROOT / "streamlit_app.py", destination / "streamlit_app.py")
    package = destination / "src" / "data_ana"
    package.mkdir(parents=True, exist_ok=True)
    for source in sorted((ROOT / "src" / "data_ana").iterdir()):
        if source.is_file() and source.suffix in {".py", ".sql"}:
            shutil.copy2(source, package / source.name)
    data = destination / "data" / "raw"
    data.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "data" / "raw" / "jobs.csv", data / "jobs.csv")
    return destination


if __name__ == "__main__":
    print(prepare())
