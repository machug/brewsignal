"""BeerXML 1.0 parser service.

Parses BeerXML files and extracts fermentation-relevant data:
- Recipe name, author, type
- OG/FG targets
- Yeast name, temp range, attenuation
- Style information
"""

from dataclasses import dataclass, field
from typing import Optional

import defusedxml.ElementTree as ET


@dataclass
class ParsedYeast:
    """Yeast data extracted from BeerXML."""
    name: Optional[str] = None
    lab: Optional[str] = None
    product_id: Optional[str] = None
    temp_min: Optional[float] = None  # Celsius
    temp_max: Optional[float] = None  # Celsius
    attenuation: Optional[float] = None


@dataclass
class ParsedStyle:
    """Style data extracted from BeerXML."""
    name: Optional[str] = None
    category: Optional[str] = None
    category_number: Optional[str] = None
    style_letter: Optional[str] = None
    guide: Optional[str] = None


@dataclass
class ParsedFermentable:
    """Fermentable ingredient data."""
    name: str
    type: Optional[str] = None
    amount_kg: Optional[float] = None
    yield_percent: Optional[float] = None
    color_lovibond: Optional[float] = None
    origin: Optional[str] = None
    supplier: Optional[str] = None
    notes: Optional[str] = None
    add_after_boil: Optional[bool] = None
    coarse_fine_diff: Optional[float] = None
    moisture: Optional[float] = None
    diastatic_power: Optional[float] = None
    protein: Optional[float] = None
    max_in_batch: Optional[float] = None
    recommend_mash: Optional[bool] = None


@dataclass
class ParsedHop:
    """Hop data extracted from BeerXML."""
    name: str
    alpha_percent: Optional[float] = None
    amount_kg: Optional[float] = None
    use: Optional[str] = None
    time_min: Optional[float] = None
    form: Optional[str] = None
    type: Optional[str] = None
    origin: Optional[str] = None
    substitutes: Optional[str] = None
    beta_percent: Optional[float] = None
    hsi: Optional[float] = None
    humulene: Optional[float] = None
    caryophyllene: Optional[float] = None
    cohumulone: Optional[float] = None
    myrcene: Optional[float] = None
    notes: Optional[str] = None


@dataclass
class ParsedRecipe:
    """Recipe data extracted from BeerXML."""
    name: str
    author: Optional[str] = None
    type: Optional[str] = None
    og: Optional[float] = None
    fg: Optional[float] = None
    ibu: Optional[float] = None
    srm: Optional[float] = None
    abv: Optional[float] = None
    batch_size: Optional[float] = None  # Liters
    style: Optional[ParsedStyle] = None
    yeast: Optional[ParsedYeast] = None
    fermentables: list[ParsedFermentable] = field(default_factory=list)
    hops: list[ParsedHop] = field(default_factory=list)
    raw_xml: str = ""


def parse_beerxml(xml_content: str) -> list[ParsedRecipe]:
    """Parse BeerXML content and return list of recipes.

    Args:
        xml_content: BeerXML 1.0 formatted XML string

    Returns:
        List of ParsedRecipe dataclasses with extracted data

    Raises:
        ET.ParseError: If XML is malformed
    """
    root = ET.fromstring(xml_content)
    recipes = []

    for recipe_elem in root.findall('.//RECIPE'):
        recipe = _parse_recipe(recipe_elem, xml_content)
        recipes.append(recipe)

    return recipes


def _get_text(elem, tag: str) -> Optional[str]:
    """Get text content of child element."""
    child = elem.find(tag)
    return child.text.strip() if child is not None and child.text else None


def _get_float(elem, tag: str) -> Optional[float]:
    """Get float value of child element."""
    text = _get_text(elem, tag)
    if text:
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _parse_fermentables(recipe_elem) -> list[ParsedFermentable]:
    """Parse FERMENTABLES section."""
    fermentables = []

    for ferm_elem in recipe_elem.findall('.//FERMENTABLES/FERMENTABLE'):
        fermentable = ParsedFermentable(
            name=_get_text(ferm_elem, 'NAME') or "Unknown",
            type=_get_text(ferm_elem, 'TYPE'),
            amount_kg=_get_float(ferm_elem, 'AMOUNT'),
            yield_percent=_get_float(ferm_elem, 'YIELD'),
            color_lovibond=_get_float(ferm_elem, 'COLOR'),
            origin=_get_text(ferm_elem, 'ORIGIN'),
            supplier=_get_text(ferm_elem, 'SUPPLIER'),
            notes=_get_text(ferm_elem, 'NOTES'),
            add_after_boil=_get_text(ferm_elem, 'ADD_AFTER_BOIL') == 'TRUE',
            coarse_fine_diff=_get_float(ferm_elem, 'COARSE_FINE_DIFF'),
            moisture=_get_float(ferm_elem, 'MOISTURE'),
            diastatic_power=_get_float(ferm_elem, 'DIASTATIC_POWER'),
            protein=_get_float(ferm_elem, 'PROTEIN'),
            max_in_batch=_get_float(ferm_elem, 'MAX_IN_BATCH'),
            recommend_mash=_get_text(ferm_elem, 'RECOMMEND_MASH') == 'TRUE',
        )
        fermentables.append(fermentable)

    return fermentables


def _parse_hops(recipe_elem) -> list[ParsedHop]:
    """Parse HOPS section."""
    hops = []
    for hop_elem in recipe_elem.findall('.//HOPS/HOP'):
        hop = ParsedHop(
            name=_get_text(hop_elem, 'NAME') or "Unknown",
            alpha_percent=_get_float(hop_elem, 'ALPHA'),
            amount_kg=_get_float(hop_elem, 'AMOUNT'),
            use=_get_text(hop_elem, 'USE'),
            time_min=_get_float(hop_elem, 'TIME'),
            form=_get_text(hop_elem, 'FORM'),
            type=_get_text(hop_elem, 'TYPE'),
            origin=_get_text(hop_elem, 'ORIGIN'),
            substitutes=_get_text(hop_elem, 'SUBSTITUTES'),
            beta_percent=_get_float(hop_elem, 'BETA'),
            hsi=_get_float(hop_elem, 'HSI'),
            humulene=_get_float(hop_elem, 'HUMULENE'),
            caryophyllene=_get_float(hop_elem, 'CARYOPHYLLENE'),
            cohumulone=_get_float(hop_elem, 'COHUMULONE'),
            myrcene=_get_float(hop_elem, 'MYRCENE'),
            notes=_get_text(hop_elem, 'NOTES'),
        )
        hops.append(hop)
    return hops


def _parse_recipe(elem, raw_xml: str) -> ParsedRecipe:
    """Parse a single RECIPE element."""
    recipe = ParsedRecipe(
        name=_get_text(elem, 'NAME') or "Unnamed Recipe",
        author=_get_text(elem, 'BREWER'),
        type=_get_text(elem, 'TYPE'),
        og=_get_float(elem, 'OG'),
        fg=_get_float(elem, 'FG'),
        ibu=_get_float(elem, 'IBU'),
        srm=_get_float(elem, 'EST_COLOR'),
        abv=_get_float(elem, 'EST_ABV'),
        batch_size=_get_float(elem, 'BATCH_SIZE'),
        raw_xml=raw_xml
    )

    # Parse style
    style_elem = elem.find('.//STYLE')
    if style_elem is not None:
        recipe.style = ParsedStyle(
            name=_get_text(style_elem, 'NAME'),
            category=_get_text(style_elem, 'CATEGORY'),
            category_number=_get_text(style_elem, 'CATEGORY_NUMBER'),
            style_letter=_get_text(style_elem, 'STYLE_LETTER'),
            guide=_get_text(style_elem, 'STYLE_GUIDE'),
        )

    # Parse first yeast
    yeast_elem = elem.find('.//YEASTS/YEAST')
    if yeast_elem is not None:
        recipe.yeast = ParsedYeast(
            name=_get_text(yeast_elem, 'NAME'),
            lab=_get_text(yeast_elem, 'LABORATORY'),
            product_id=_get_text(yeast_elem, 'PRODUCT_ID'),
            temp_min=_get_float(yeast_elem, 'MIN_TEMPERATURE'),
            temp_max=_get_float(yeast_elem, 'MAX_TEMPERATURE'),
            attenuation=_get_float(yeast_elem, 'ATTENUATION'),
        )

    # Parse fermentables
    recipe.fermentables = _parse_fermentables(elem)

    # Parse hops
    recipe.hops = _parse_hops(elem)

    return recipe
