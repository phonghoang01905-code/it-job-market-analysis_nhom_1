"""Week 3 entry point; works directly from the repository checkout."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

if __name__ == "__main__":
    from data_ana.pipeline import main
    raise SystemExit(main())
