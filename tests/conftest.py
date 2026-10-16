"""Chargement des modules métier sans dépendre de Home Assistant.

Le paquet de l'intégration importe Home Assistant dans son __init__ ; on enregistre
donc un paquet synthétique pointant sur le même dossier pour charger uniquement
les modules purs (parser, location, const).
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
PKG_DIR = ROOT / "custom_components" / "efs_dondesang"

_pkg = types.ModuleType("efs_pkg")
_pkg.__path__ = [str(PKG_DIR)]
sys.modules.setdefault("efs_pkg", _pkg)

parser = importlib.import_module("efs_pkg.parser")
location = importlib.import_module("efs_pkg.location")


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))
