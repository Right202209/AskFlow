"""让 eval 包在未 editable-install 的环境下也能 import askflow（与 scripts/ 同套路）。"""

from __future__ import annotations

import os
import sys

_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
