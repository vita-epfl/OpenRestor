#!/usr/bin/env python3
"""Build fail-closed publication profiles from the private per-media rights register.

See openrestor.publication_cli for the implementation. No whole partition is copied.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openrestor.publication_cli import main


if __name__ == "__main__":
    main()
