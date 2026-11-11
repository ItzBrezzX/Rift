"""Compatibility imports for the v0.1 analyzer entry points."""

from app.detection.analyzer import analyze_entries
from app.security.archive import UnsafeArchiveError, validate_zip_names

__all__ = ["analyze_entries", "UnsafeArchiveError", "validate_zip_names"]
