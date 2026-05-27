"""Validation rules for extract vs traditional hops (tilt_ui-0l5 phase 1)."""
import pytest
from backend.services.serializers.recipe_serializer import RecipeSerializer


@pytest.fixture
def serializer():
    return RecipeSerializer()


def test_extract_with_boil_use_rejected(serializer):
    """Extracts are cold-side only — boil must raise."""
    bad = {
        "name": "Quantum MOS",
        "is_extract": True,
        "amount_ml": 2.5,
        "timing": {"use": "boil", "duration": {"value": 60}},
    }
    with pytest.raises(ValueError, match=r"cold-side|extract.*boil|boil.*extract"):
        serializer._create_hop(bad)


def test_extract_with_whirlpool_use_rejected(serializer):
    """Whirlpool is hot-side — rejected for extracts."""
    bad = {
        "name": "Quantum CIT",
        "is_extract": True,
        "amount_ml": 1.5,
        "timing": {"use": "whirlpool", "duration": {"value": 20}},
    }
    with pytest.raises(ValueError, match=r"cold-side|whirlpool"):
        serializer._create_hop(bad)


def test_extract_requires_amount_ml(serializer):
    bad = {
        "name": "Quantum KRU",
        "is_extract": True,
        "timing": {"use": "dry_hop", "duration": {"value": 0}},
    }
    with pytest.raises(ValueError, match=r"amount_ml"):
        serializer._create_hop(bad)


def test_extract_zero_amount_ml_rejected(serializer):
    bad = {
        "name": "Quantum KRU",
        "is_extract": True,
        "amount_ml": 0,
        "timing": {"use": "dry_hop", "duration": {"value": 0}},
    }
    with pytest.raises(ValueError, match=r"amount_ml"):
        serializer._create_hop(bad)


def test_non_extract_still_requires_alpha(serializer):
    bad = {
        "name": "Mosaic",
        "amount": {"value": 20, "unit": "g"},
        "timing": {"use": "boil", "duration": {"value": 60}},
    }
    with pytest.raises(ValueError, match=r"alpha"):
        serializer._create_hop(bad)


def test_extract_with_dry_hop_use_accepted(serializer):
    """Cold-side timing is OK for extracts."""
    ok = {
        "name": "Quantum MOS",
        "is_extract": True,
        "amount_ml": 2.5,
        "timing": {"use": "dry_hop", "duration": {"value": 0}},
    }
    hop = serializer._create_hop(ok)
    assert hop.is_extract is True
    assert hop.amount_ml == 2.5


def test_extract_without_timing_accepted(serializer):
    """If no timing is provided, default to cold-side semantics — accept."""
    ok = {
        "name": "Quantum MOS",
        "is_extract": True,
        "amount_ml": 1.0,
    }
    hop = serializer._create_hop(ok)
    assert hop.is_extract is True


def test_pellet_with_alpha_accepted(serializer):
    ok = {
        "name": "Mosaic",
        "alpha_acid": {"value": 0.12, "unit": "%"},
        "amount": {"value": 20, "unit": "g"},
        "timing": {"use": "boil", "duration": {"value": 60}},
    }
    hop = serializer._create_hop(ok)
    assert hop.alpha_acid_percent is not None
    assert hop.amount_grams == 20


def test_extract_with_add_to_fermentation_accepted(serializer):
    ok = {
        "name": "Quantum NSN",
        "is_extract": True,
        "amount_ml": 1.0,
        "timing": {"use": "add_to_fermentation", "duration": {"value": 0}},
    }
    hop = serializer._create_hop(ok)
    assert hop.is_extract is True


def test_extract_with_add_to_package_accepted(serializer):
    ok = {
        "name": "Quantum STT",
        "is_extract": True,
        "amount_ml": 1.0,
        "timing": {"use": "add_to_package", "duration": {"value": 0}},
    }
    hop = serializer._create_hop(ok)
    assert hop.is_extract is True


def test_non_extract_with_zero_alpha_rejected(serializer):
    """Converters historically defaulted missing alpha to 0.0; that must not
    bypass alpha-required validation (tilt_ui-0l5)."""
    bad = {
        "name": "Mosaic",
        "alpha_acid": 0.0,
        "amount": {"value": 20, "unit": "g"},
        "timing": {"use": "boil", "duration": {"value": 60}},
    }
    with pytest.raises(ValueError, match=r"alpha"):
        serializer._create_hop(bad)


def test_alpha_alias_persists_to_orm(serializer):
    """Validator accepts alpha under multiple aliases; _create_hop must
    persist them all to alpha_acid_percent (tilt_ui-0l5)."""
    for alias in ("alpha_acid_percent", "alpha"):
        ok = {
            "name": f"Test {alias}",
            alias: {"value": 0.12, "unit": "%"},
            "amount": {"value": 20, "unit": "g"},
            "timing": {"use": "boil", "duration": {"value": 60}},
        }
        hop = serializer._create_hop(ok)
        assert hop.alpha_acid_percent is not None, (
            f"alias {alias!r} accepted by validator but lost during _create_hop"
        )
        assert hop.alpha_acid_percent > 0
