"""Test Brewfather JSON to BeerJSON converter."""
import pytest
import json
from backend.services.converters.brewfather_to_beerjson import BrewfatherToBeerJSONConverter


def test_convert_brewfather_json_to_beerjson():
    """Test converting Brewfather JSON to BeerJSON."""
    # Load Brewfather JSON
    with open("docs/Brewfather_RECIPE_PhilterXPAClone_20251207.json", "r") as f:
        brewfather_dict = json.load(f)

    # Convert to BeerJSON
    converter = BrewfatherToBeerJSONConverter()
    beerjson = converter.convert(brewfather_dict)

    # Verify BeerJSON structure
    assert 'beerjson' in beerjson
    assert 'version' in beerjson['beerjson']
    assert beerjson['beerjson']['version'] == 1.0
    assert 'recipes' in beerjson['beerjson']

    recipe = beerjson['beerjson']['recipes'][0]

    # Verify basic fields
    assert recipe['name'] == "Philter XPA - Clone"
    assert recipe['type'] == "all grain"
    assert recipe['author'] == "Pig Den Brewing"

    # Verify batch size (liters)
    assert recipe['batch_size']['value'] == 21.0
    assert recipe['batch_size']['unit'] == "l"

    # Verify gravity
    assert recipe['original_gravity']['value'] == pytest.approx(1.040069094)
    assert recipe['final_gravity']['value'] == pytest.approx(1.008)

    # Verify ABV
    assert recipe['alcohol_by_volume']['value'] == pytest.approx(0.042, rel=0.01)

    # Verify IBU
    assert recipe['ibu_estimate']['value'] == pytest.approx(28.7)

    # Verify color
    assert recipe['color_estimate']['value'] == pytest.approx(3.8)
    assert recipe['color_estimate']['unit'] == "SRM"

    # Verify carbonation (BeerJSON expects number, not object)
    assert recipe['carbonation'] == pytest.approx(2.4)

    # Verify efficiency
    assert 'efficiency' in recipe
    assert recipe['efficiency']['brewhouse']['value'] == pytest.approx(0.73)

    # Verify boil
    assert 'boil' in recipe
    assert recipe['boil']['boil_time']['value'] == 60
    assert recipe['boil']['boil_time']['unit'] == 'min'

    # Verify ingredients
    assert 'ingredients' in recipe
    assert len(recipe['ingredients']['fermentable_additions']) == 4
    assert len(recipe['ingredients']['hop_additions']) == 6
    assert len(recipe['ingredients']['culture_additions']) == 1
    assert len(recipe['ingredients']['miscellaneous_additions']) == 8

    # Verify fermentable conversion
    ale_malt = next(
        f for f in recipe['ingredients']['fermentable_additions']
        if f['name'] == 'Ale Malt'
    )
    assert ale_malt['amount']['value'] == pytest.approx(2.733)
    assert ale_malt['amount']['unit'] == 'kg'
    assert ale_malt['producer'] == 'Gladfield'
    assert ale_malt['origin'] == 'New Zealand'
    assert ale_malt['type'] == 'grain'
    assert ale_malt['color']['value'] == pytest.approx(3.0456853)
    assert ale_malt['color']['unit'] == 'SRM'

    # Verify hop timing (hopstand/whirlpool)
    # Find first hop with duration 30 (the hopstand)
    citra_hopstand = next(
        h for h in recipe['ingredients']['hop_additions']
        if h['name'] == 'Citra' and h['timing'].get('duration', {}).get('value') == 30
    )
    assert citra_hopstand['timing']['use'] == 'add_to_boil'
    assert citra_hopstand['timing']['duration']['value'] == 30
    assert citra_hopstand['amount']['value'] == 46
    assert citra_hopstand['amount']['unit'] == 'g'
    assert citra_hopstand['alpha_acid']['value'] == pytest.approx(0.141)

    # Verify dry hop
    citra_dryhop = next(
        h for h in recipe['ingredients']['hop_additions']
        if h['name'] == 'Citra' and h['timing']['use'] == 'add_to_fermentation'
    )
    assert citra_dryhop['timing']['use'] == 'add_to_fermentation'
    assert citra_dryhop['timing']['duration']['value'] == 4
    assert citra_dryhop['timing']['duration']['unit'] == 'day'
    assert citra_dryhop['amount']['value'] == 31.5

    # Verify yeast/culture
    yeast = recipe['ingredients']['culture_additions'][0]
    assert yeast['name'] == "Safale American"
    assert yeast['producer'] == "Fermentis"
    assert yeast['product_id'] == "US-05"
    assert yeast['type'] == 'ale'
    assert yeast['form'] == 'dry'
    assert yeast['attenuation_range']['minimum']['value'] == pytest.approx(0.81)
    assert yeast['attenuation_range']['maximum']['value'] == pytest.approx(0.81)
    assert yeast['temperature_range']['minimum']['value'] == 16
    assert yeast['temperature_range']['maximum']['value'] == 28
    assert yeast['amount']['value'] == 1
    assert yeast['amount']['unit'] == 'pkg'

    # Verify mash steps
    assert 'mash' in recipe
    assert len(recipe['mash']['mash_steps']) == 3
    assert recipe['mash']['mash_steps'][0]['name'] == "Mash in"
    assert recipe['mash']['mash_steps'][0]['step_temperature']['value'] == 55
    assert recipe['mash']['mash_steps'][0]['step_time']['value'] == 10

    # NOTE: Water chemistry and _extensions are removed for BeerJSON 1.0 spec compliance
    # BeerJSON schema has additionalProperties: false on RecipeType

    # Verify style
    assert 'style' in recipe
    assert recipe['style']['name'] == "Australian-Style Pale Ale"
    assert recipe['style']['category'] == "Other Origin Ale"
    assert recipe['style']['style_guide'] == "Brewers Association 2019"
    assert recipe['style']['type'] == 'beer'

    # Verify fermentation steps
    assert 'fermentation' in recipe
    assert len(recipe['fermentation']['fermentation_steps']) == 1
    assert recipe['fermentation']['fermentation_steps'][0]['name'] == 'Primary'
    assert recipe['fermentation']['fermentation_steps'][0]['start_temperature']['value'] == 20
    assert recipe['fermentation']['fermentation_steps'][0]['end_temperature']['value'] == 20
    assert recipe['fermentation']['fermentation_steps'][0]['step_time']['value'] == 14
    assert recipe['fermentation']['fermentation_steps'][0]['step_time']['unit'] == 'day'
