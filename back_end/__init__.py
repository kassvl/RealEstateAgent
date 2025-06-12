"""Backend package init to enable absolute imports.
Sets project root on sys.path if necessary."""
import sys
from pathlib import Path

# Ensure project root in sys.path for child modules when executed via Celery
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Ensure back_end directory itself is also on sys.path so that modules inside
# can be imported with "from cache import ..." style absolute imports, even
# when the entry-point is outside the package (e.g. Celery)
backend_path = Path(__file__).resolve().parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))
