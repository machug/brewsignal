"""The one recipe-stats calculator (tilt_ui-4x2f.1). In-memory ORM objects, no DB."""
import pytest

from backend.models import Recipe, RecipeCulture, RecipeFermentable, RecipeHop
from backend.services.brewing import (
    CalculatedStats,
    calculate_recipe_stats,
    get_attenuation_from_cultures,
    srm_to_hex,
)


def ferm(name="Pale Ale", kg=1.0, yld=82.8, srm=3.0, type_="grain"):
    return RecipeFermentable(name=name, amount_kg=kg, yield_percent=yld, color_srm=srm, type=type_)


def hop(name="H", g=20, aa=10.0, use="add_to_boil", dur=60, unit="min", temp=None, form="pellet"):
    timing = {"use": use, "duration": {"value": dur, "unit": unit}}
    if temp is not None:
        timing["temperature"] = {"value": temp, "unit": "C"}
    return RecipeHop(name=name, amount_grams=g, alpha_acid_percent=aa, form=form, timing=timing)


def recipe(ferms, hops=(), cultures=(), eff=73.0, batch=23.0, atten=None):
    return Recipe(
        name="t", fermentables=list(ferms), hops=list(hops), cultures=list(cultures),
        efficiency_percent=eff, batch_size_liters=batch, yeast_attenuation=atten,
    )


def culture(lo=None, hi=None):
    return RecipeCulture(name="Y", attenuation_min_percent=lo, attenuation_max_percent=hi)


def test_recipe_32_golden():
    r = recipe(
        [ferm("Pale Ale", 2.30, 82.8, 3), ferm("Pilsen Malt", 2.30, 82.8, 1.6),
         ferm("Carapils", 0.252, 73.0, 1.5), ferm("Melanoidin", 0.151, 77.0, 28)],
        [hop("El Dorado", 15, 15, dur=60),
         hop("Cascade", 20, 5.8, dur=10),
         hop("Cascade", 40, 5.8, use="add_to_whirlpool", dur=20, temp=80),
         hop("Amarillo", 30, 8.5, use="add_to_whirlpool", dur=20, temp=80)]
        + [hop(f"Dry{i}", 30, 10, use="add_to_fermentation", dur=3, unit="day") for i in range(3)],
        [culture(72, 78)],
    )
    s = calculate_recipe_stats(r)
    assert isinstance(s, CalculatedStats)
    assert s.og == pytest.approx(1.050, abs=0.001)
    assert s.ibu == pytest.approx(37, abs=1.5)
    assert s.fg == pytest.approx(1.0125, abs=0.001)
    assert s.assumptions == ()


def test_no_fermentables_returns_none():
    assert calculate_recipe_stats(recipe([], [hop()])) is None


def test_attenuation_midpoint_then_recipe_then_default():
    assert get_attenuation_from_cultures([culture(72, 78)]) == pytest.approx(0.75)
    assert get_attenuation_from_cultures([culture(None, 80)]) == pytest.approx(0.80)
    assert get_attenuation_from_cultures([culture()], 70) == pytest.approx(0.70)
    notes = []
    assert get_attenuation_from_cultures([], None, notes) == pytest.approx(0.75)
    assert notes == ["Assumed 75% yeast attenuation"]
    s = calculate_recipe_stats(recipe([ferm()], cultures=[culture(80, 80)]))
    assert s.fg == pytest.approx(1 + (s.og - 1) * 0.2, abs=0.001)
    assert "Assumed 75% yeast attenuation" not in s.assumptions


def test_duration_units_normalised():
    base = [ferm()]
    def ibu(**kw):
        return calculate_recipe_stats(recipe(base, [hop(**kw)])).ibu
    assert ibu(dur=1, unit="hr") == ibu(dur=60, unit="min") > 0
    assert ibu(use="add_to_fermentation", dur=4, unit="day") == 0
    assert ibu(dur=0) == 0


def test_missing_inputs_listed_in_assumptions():
    r = Recipe(
        name="t", batch_size_liters=None, efficiency_percent=None, yeast_attenuation=None,
        fermentables=[RecipeFermentable(name="Mystery Grain", amount_kg=3)],
        hops=[RecipeHop(name="Mystery Hop", amount_grams=30, alpha_acid_percent=None, form="pellet",
                        timing={"use": "add_to_whirlpool", "duration": {"value": 20, "unit": "min"}})],
        cultures=[],
    )
    s = calculate_recipe_stats(r)
    assert set(s.assumptions) == {
        "Assumed 20 L batch",
        "Assumed 75% brewhouse efficiency",
        "Estimated yield for Mystery Grain",
        "Estimated colour for Mystery Grain",
        "Assumed 5% alpha for Mystery Hop",
        "No whirlpool temperature for Mystery Hop: counted as boiling",
        "Assumed 75% yeast attenuation",
    }
    assert len(s.assumptions) == 7


def test_sugar_ignores_efficiency():
    def pts(eff):
        s = calculate_recipe_stats(recipe([ferm("Dextrose", 0.5, 100, 0, "sugar")], eff=eff))
        return s.og
    assert pts(50) == pytest.approx(pts(90))


def test_srm_uncapped_hex_clamped():
    r = recipe([ferm("Pale", 5, 80, 3), ferm("Roasted Barley", 1.5, 70, 500), ferm("Black", 0.5, 70, 500)],
               batch=20)
    s = calculate_recipe_stats(r)
    assert s.srm > 40
    assert s.color_hex == srm_to_hex(40) == "#261000"


def test_bu_gu_and_calories():
    # Hand-worked with the frontend formulas (calculateBUGU, calculateCalories; no
    # vitest cases exist): 54.0 IBU / 43 gravity points = 1.26;
    # (4.51% * 0.79 * 7 + 0.009 * 1000 * 0.4) * 3.3 = 94 kcal.
    r = recipe([ferm("Pale", 4.0, 80, 3)], [hop(g=40, aa=10)], [culture(80, 80)], eff=70, batch=20)
    s = calculate_recipe_stats(r)
    assert (s.og, s.fg, s.ibu) == (1.043, 1.009, 54.0)
    assert s.bu_gu == 1.26
    assert s.calories_per_330ml == 94
    assert srm_to_hex(1) == "#FFE699" and srm_to_hex(6.5) == "#F8A600"
