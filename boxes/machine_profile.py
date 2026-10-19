# Copyright (C) 2026 Chris (ChrisLaserman)
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Machine profile: per-laser defaults loaded from a YAML file.

The profile is looked up in this order:

1. the file named by the BOXES_PROFILE environment variable
2. ``machine_profile.yaml`` in the repository root

If neither exists nothing changes and boxes behaves exactly like upstream.

The profile can set:

* ``defaults``: argument defaults applied to every generator (e.g.
  thickness, burn, format). Only arguments a generator actually has are
  touched, and anything given on the command line or in the web form still
  wins.
* ``layers``: LightBurn cut settings (speed in mm/s, power in percent,
  passes) written into .lbrn2 output, keyed by LightBurn layer index.
"""

from __future__ import annotations

import argparse
import os
from functools import cache
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "machine_profile.yaml"


@cache
def load() -> dict[str, Any]:
    path = os.environ.get("BOXES_PROFILE")
    p = Path(path) if path else DEFAULT_PATH
    if not p.is_file():
        return {}
    with open(p) as f:
        return yaml.safe_load(f) or {}


def apply_defaults(argparser: argparse.ArgumentParser) -> None:
    defaults = load().get("defaults") or {}
    dests = {a.dest for a in argparser._actions}
    argparser.set_defaults(**{k: v for k, v in defaults.items() if k in dests})


def layer_settings(index: int) -> dict[str, Any]:
    """LightBurn cut settings for the layer with the given color index"""
    return (load().get("layers") or {}).get(index) or {}
