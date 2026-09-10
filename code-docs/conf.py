import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

project = "OpenRestore"
author = "EPFL ENAC IT4R"
copyright = "EPFL ENAC IT4R"
release = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "myst_parser",
]
html_theme = "sphinx_rtd_theme"

autodoc_mock_imports = []
