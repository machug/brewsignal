"""Tests for BeerXML parser."""
import pytest
from backend.services.parsers.beerxml_parser import BeerXMLParser


def test_parse_brewfather_beerxml():
    """Test parsing Brewfather BeerXML export (Philter XPA)."""
    with open("docs/Brewfather_BeerXML_PhilterXPAClone_20251207.xml", "r") as f:
        xml_content = f.read()

    parser = BeerXMLParser()
    result = parser.parse(xml_content)

    # Verify structure
    assert 'RECIPES' in result
    assert 'RECIPE' in result['RECIPES']

    recipe = result['RECIPES']['RECIPE']

    # Verify basic fields
    assert recipe['NAME'] == "Philter XPA - Clone"
    assert recipe['TYPE'] == "All Grain"
    assert recipe['BREWER'] == "Pig Den Brewing"
    assert float(recipe['BATCH_SIZE']) == 21.0
    assert float(recipe['OG']) == 1.040

    # Verify ingredients
    assert 'FERMENTABLES' in recipe
    assert 'FERMENTABLE' in recipe['FERMENTABLES']
    assert len(recipe['FERMENTABLES']['FERMENTABLE']) == 4

    assert 'HOPS' in recipe
    assert 'HOP' in recipe['HOPS']
    assert len(recipe['HOPS']['HOP']) == 6

    # Verify hopstand temperature (Brewfather extension)
    citra_hop = next(h for h in recipe['HOPS']['HOP']
                     if h['NAME'] == 'Citra' and h['USE'] == 'Aroma')
    assert 'TEMPERATURE' in citra_hop
    assert int(citra_hop['TEMPERATURE']) == 80
