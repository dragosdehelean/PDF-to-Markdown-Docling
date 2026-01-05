"""@fileoverview Unit tests for spacing detection heuristics."""

from __future__ import annotations

from audit_utils import (
    is_collapsed_text,
    is_spaced_text,
    needs_spacing_fix,
    needs_table_spacing_fix,
)


def test_spacing_detection_basic() -> None:
    """Validate base spacing detection for split letters and digits."""
    assert is_spaced_text("1 2 3 4") is True
    assert is_spaced_text("Indi c a t ori") is True
    assert is_spaced_text("Indicatori") is False


def test_collapsed_text_detection() -> None:
    """Ensure run-on text triggers collapsed detection."""
    run_on = "politicacompanieideoptimizareastructuriidatoriilor"
    assert is_collapsed_text(run_on) is True
    assert is_collapsed_text("Text normal cu spatii") is False


def test_needs_spacing_fix_dispatch() -> None:
    """Confirm generic spacing fix decision combines split and run-on cases."""
    assert needs_spacing_fix("A B C D") is True
    assert needs_spacing_fix("Text normal") is False


def test_table_spacing_detection_targets_short_splits() -> None:
    """Verify table-specific detection catches short split tokens."""
    assert needs_table_spacing_fix("E U") is True
    assert needs_table_spacing_fix("CIFRA DE AFACERI NET Ă") is True
    assert needs_table_spacing_fix("1.  Produ cț ia  vâ ndu tă") is True
    assert needs_table_spacing_fix("Indicatori") is False
    assert needs_table_spacing_fix("Producția vândută") is False
    assert needs_table_spacing_fix("158.065.856") is False
