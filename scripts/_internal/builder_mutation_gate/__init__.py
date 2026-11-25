# -*- coding: utf-8 -*-
"""Pacchetto interno builder_mutation_gate per mutation testing differenziale e audit AST."""

from __future__ import annotations

import pkgutil

__path__ = pkgutil.extend_path(__path__, __name__)

from _internal.builder_mutation_gate.audit_mode import (  # noqa: E402
    SharedBaseNVMeWorkerPool,
    run_full_module_audit,
    run_multi_module_audit,
)
from _internal.builder_mutation_gate.hotspot_audit import (  # noqa: E402
    select_hotspot_functions,
)
from _internal.builder_mutation_gate.mutant_gen import (  # noqa: E402
    MutantSpec,
    find_touched_functions,
    generate_audit_mutants,
    generate_differential_mutants,
)
from _internal.builder_mutation_gate.runner import (  # noqa: E402
    MutantOutcome,
    MutationGateReport,
    run_mutation_gate,
)

__all__ = [
    "MutantOutcome",
    "MutantSpec",
    "MutationGateReport",
    "SharedBaseNVMeWorkerPool",
    "find_touched_functions",
    "generate_audit_mutants",
    "generate_differential_mutants",
    "run_full_module_audit",
    "run_multi_module_audit",
    "run_mutation_gate",
    "select_hotspot_functions",
]
