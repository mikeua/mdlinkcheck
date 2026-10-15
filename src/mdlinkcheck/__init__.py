"""Find broken relative links and #anchors in Markdown files."""

from .checker import Checker, Options, Problem
from .markdown import parse
from .slug import Slugger, slugify

__version__ = "0.2.1"

__all__ = ["Checker", "Options", "Problem", "Slugger", "parse", "slugify", "__version__"]
