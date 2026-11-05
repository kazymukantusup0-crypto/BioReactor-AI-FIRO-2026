"""Scientific BMP research pipeline."""
from pathlib import Path
import sys

# Optional project-local binary dependencies, shared by CLI, API and pytest.
_runtime = Path(__file__).resolve().parent.parent / '.runtime-deps'
if _runtime.is_dir() and str(_runtime) not in sys.path:
    sys.path.insert(0, str(_runtime))
