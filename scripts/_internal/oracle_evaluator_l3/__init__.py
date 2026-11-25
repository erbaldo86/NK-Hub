# -*- coding: utf-8 -*-
"""Pacchetto interno per il valutatore DOM L3 e Oracolo E2E."""

from __future__ import annotations

import tempfile
from pathlib import Path

_INITIAL_SYSTEM_TEMP: Path = Path(tempfile.gettempdir()).resolve()
