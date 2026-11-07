"""Start Miso without a console window (double-click or autostart)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from miso.app import main  # noqa: E402

sys.exit(main())
