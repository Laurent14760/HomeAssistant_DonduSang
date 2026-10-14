"""Chargement du module métier sans dépendre de Home Assistant."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
_PARSER_PATH = ROOT / "custom_components" / "efs_dondesang" / "parser.py"

_spec = importlib.util.spec_from_file_location("efs_parser", _PARSER_PATH)
parser = importlib.util.module_from_spec(_spec)
sys.modules["efs_parser"] = parser
_spec.loader.exec_module(parser)


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))
