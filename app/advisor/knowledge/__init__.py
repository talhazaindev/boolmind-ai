"""Static knowledge bases for Boolmind Advisor."""

from app.advisor.knowledge.ontology_loader import match_archetypes, match_archetypes_sync
from app.advisor.knowledge.ontology_schema import BusinessArchetype

__all__ = ["BusinessArchetype", "match_archetypes", "match_archetypes_sync"]
