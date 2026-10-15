# -*- coding: utf-8 -*-
"""
Configurazione Pytest e fixture globali per la suite di test Nexus Keystone v3.0.0.
"""

import sys
import tempfile
import shutil
import pytest
from pathlib import Path

# Add scripts directory to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
STAGING_DIR = CURRENT_DIR.parent
SCRIPTS_DIR = STAGING_DIR / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(STAGING_DIR) not in sys.path:
    sys.path.insert(0, str(STAGING_DIR))


@pytest.fixture
def temp_test_dir():
    """Fornisce una directory temporanea isolata per le operazioni di test."""
    tmp = tempfile.mkdtemp(prefix="nk_test_dir_")
    path = Path(tmp)
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def clean_sandbox_dir():
    """Fornisce una directory sandbox isolata per i test."""
    tmp = tempfile.mkdtemp(prefix="nk_sandbox_test_")
    path = Path(tmp)
    yield path
    shutil.rmtree(path, ignore_errors=True)
