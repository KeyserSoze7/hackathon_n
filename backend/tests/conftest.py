import os
import pathlib
import sys

os.environ.setdefault("STRICT_MODELS", "1")  # undeclared/mistyped response fields fail loudly
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # backend/
