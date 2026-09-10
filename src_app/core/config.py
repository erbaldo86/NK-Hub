"""LabNK Core Configuration Constants.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""

from typing import Final

# Upload & Streaming Limits
MAX_UPLOAD_SIZE: Final[int] = 25 * 1024 * 1024  # 25 MB max upload security cap
CHUNK_SIZE: Final[int] = 1024 * 1024            # 1 MB streaming read chunk

# Search & Retrieval Defaults
DEFAULT_TOP_K: Final[int] = 20
MAX_TOP_K: Final[int] = 100
MIN_TOP_K: Final[int] = 1

# Financial & Regulatory Thresholds
DE_MINIMIS_THRESHOLD: Final[float] = 300_000.0  # Massimale europeo aiuti De Minimis (€300.000)

# In-Memory Cache Limits
MAX_LRU_DOCUMENTS: Final[int] = 50

# Application Metadata
APP_TITLE: Final[str] = "LabNK Bandi Intelligence"
APP_VERSION: Final[str] = "1.1.0-Universal"
APP_DESCRIPTION: Final[str] = (
    "Sovereign AI Grant Intelligence & Semantic Matching Platform — Nexus Keystone v1.1.0-Universal"
)
DEFAULT_HOST: Final[str] = "127.0.0.1"
DEFAULT_PORT: Final[int] = 8080
