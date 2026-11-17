# -*- coding: utf-8 -*-
"""Facciata stdlib O(1) per manifesto, shard DOM-00..DOM-06 e routing SSOT."""

from __future__ import annotations

from _internal.nk_common.catalog_loader import (
    clear_catalog_cache,
    load_all_domain_shards,
    load_domain_shard,
    load_registry_manifest,
)
from _internal.nk_common.catalog_routing import (
    get_catalog_counts,
    get_dashboard_node_map,
    get_skill_mode_map,
    get_skill_routing_rules,
    validate_catalog_contracts,
)

__all__ = [
    "clear_catalog_cache",
    "get_catalog_counts",
    "get_dashboard_node_map",
    "get_skill_mode_map",
    "get_skill_routing_rules",
    "load_all_domain_shards",
    "load_domain_shard",
    "load_registry_manifest",
    "validate_catalog_contracts",
]
