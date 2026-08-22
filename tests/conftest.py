# -*- coding: utf-8 -*-
"""
Pytest configuration and global fixtures for Nexus Keystone v1.1.0-Universal test suite.
"""

import os
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
    """Provides an isolated temporary directory for test operations."""
    tmp = tempfile.mkdtemp(prefix="nk_test_dir_")
    path = Path(tmp)
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def clean_sandbox_dir():
    """Provides an isolated sandbox test directory."""
    tmp = tempfile.mkdtemp(prefix="nk_sandbox_test_")
    path = Path(tmp)
    yield path
    shutil.rmtree(path, ignore_errors=True)
