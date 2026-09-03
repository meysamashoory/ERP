"""Pipe production-time, depot, and BOM calculation domain.

Lightweight master data + pure math engine. Line-specific details
(protect fully seeded; general/silent/pe/tip/hose/pc/round scaffolded)
can be refined later without schema churn.
"""

from .constants import LINE_CODES, NOMINAL_LENGTHS

__all__ = ["LINE_CODES", "NOMINAL_LENGTHS"]
