"""Persona System — G011."""
from .builder import (
    BUILTIN_PERSONAS,
    FORBIDDEN_GROUPS,
    AuditResult,
    PersonaSpec,
    audit_custom_persona,
    save_persona,
    seed_builtin_prompts,
)

__all__ = [
    "BUILTIN_PERSONAS",
    "FORBIDDEN_GROUPS",
    "AuditResult",
    "PersonaSpec",
    "audit_custom_persona",
    "save_persona",
    "seed_builtin_prompts",
]
