import pytest
import json
from backend.services.parsers.beerxml_parser import BeerXMLParser
from backend.services.converters.beerxml_to_beerjson import BeerXMLToBeerJSONConverter


def test_convert_brewfather_beerxml_to_beerjson():
    """Test converting Brewfather BeerXML to BeerJSON."""
    # Parse BeerXML
    with open("docs/Brewfather_BeerXML_PhilterXPAClone_20251207.xml", "r") as f:
        xml_content = f.read()

    parser = BeerXMLParser()
    beerxml_dict = parser.parse(xml_content)

    # Convert to BeerJSON
    converter = BeerXMLToBeerJSONConverter()
    beerjson = converter.convert(beerxml_dict)

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
    assert recipe['original_gravity']['value'] == pytest.approx(1.040)
    assert recipe['final_gravity']['value'] == pytest.approx(1.008)

    # Verify ingredients
    assert 'ingredients' in recipe
    assert len(recipe['ingredients']['fermentable_additions']) == 4
    assert len(recipe['ingredients']['hop_additions']) == 6
    assert len(recipe['ingredients']['culture_additions']) == 1

    # NOTE: BeerJSON 1.0 spec doesn't support hopstand temperatures
    # The BeerXML converter must comply with spec, so temperature is not preserved
    # Verify at least one hop has timing
    assert any('timing' in h for h in recipe['ingredients']['hop_additions'])

    # Verify mash steps
    assert 'mash' in recipe
    assert len(recipe['mash']['mash_steps']) == 3
    assert recipe['mash']['mash_steps'][0]['name'] == "Mash in"
    assert recipe['mash']['mash_steps'][0]['step_temperature']['value'] == 55
