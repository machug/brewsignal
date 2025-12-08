"""Service for importing BeerXML into database."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.beerxml_parser import parse_beerxml
from backend.models import (
    Recipe, RecipeFermentable, RecipeHop,
    RecipeCulture, RecipeMisc, Style
)


async def import_beerxml_to_db(db: AsyncSession, xml_content: str) -> int:
    """Import BeerXML and save to database.

    Note: If the BeerXML file contains multiple recipes, only the first recipe
    will be imported. This is the common case as most BeerXML exports contain
    a single recipe.

    Args:
        db: Database session
        xml_content: BeerXML 1.0 string

    Returns:
        Recipe ID of first imported recipe

    Raises:
        ValueError: If no recipes found in BeerXML
    """
    # Parse XML
    parsed_recipes = parse_beerxml(xml_content)
    if not parsed_recipes:
        raise ValueError("No recipes found in BeerXML")

    # Take first recipe (most BeerXML exports contain one recipe)
    parsed = parsed_recipes[0]

    # Handle style - create or find existing
    style_id = None
    if parsed.style and parsed.style.name:
        # Generate style ID from guide, category_number, and style_letter
        guide = parsed.style.guide or "unknown"
        cat_num = parsed.style.category_number or "0"
        style_letter = parsed.style.style_letter or ""
        style_id = f"{guide.lower().replace(' ', '-')}-{cat_num}{style_letter.lower()}"

        # Check if style exists
        result = await db.execute(select(Style).where(Style.id == style_id))
        existing_style = result.scalar_one_or_none()

        if not existing_style:
            # Create new style
            style = Style(
                id=style_id,
                guide=guide,
                category_number=cat_num,
                style_letter=style_letter,
                name=parsed.style.name,
                category=parsed.style.category or parsed.style.name,
                type=parsed.style.type or "Ale",
                og_min=parsed.style.og_min,
                og_max=parsed.style.og_max,
                fg_min=parsed.style.fg_min,
                fg_max=parsed.style.fg_max,
                ibu_min=parsed.style.ibu_min,
                ibu_max=parsed.style.ibu_max,
                srm_min=parsed.style.color_min,
                srm_max=parsed.style.color_max,
                abv_min=parsed.style.abv_min,
                abv_max=parsed.style.abv_max,
            )
            db.add(style)
            await db.flush()

    # Create Recipe
    recipe = Recipe(
        name=parsed.name,
        author=parsed.author,
        style_id=style_id,
        type=parsed.type,
        og=parsed.og,
        fg=parsed.fg,
        ibu=parsed.ibu,
        color_srm=parsed.srm,
        abv=parsed.abv,
        batch_size_liters=parsed.batch_size,
        beerxml_content=parsed.raw_xml,

        # Expanded BeerXML fields
        brewer=parsed.brewer,
        asst_brewer=parsed.asst_brewer,
        boil_size_l=parsed.boil_size_l,
        boil_time_minutes=int(parsed.boil_time_min) if parsed.boil_time_min else None,
        efficiency_percent=parsed.efficiency_percent,
        primary_age_days=parsed.primary_age_days,
        primary_temp_c=parsed.primary_temp_c,
        secondary_age_days=parsed.secondary_age_days,
        secondary_temp_c=parsed.secondary_temp_c,
        tertiary_age_days=parsed.tertiary_age_days,
        tertiary_temp_c=parsed.tertiary_temp_c,
        age_days=parsed.age_days,
        age_temp_c=parsed.age_temp_c,
        carbonation_vols=parsed.carbonation_vols,
        forced_carbonation=parsed.forced_carbonation,
        priming_sugar_name=parsed.priming_sugar_name,
        priming_sugar_amount_kg=parsed.priming_sugar_amount_kg,
        taste_notes=parsed.taste_notes,
        taste_rating=parsed.taste_rating,
        date=parsed.date,
    )

    # Add backward-compatible yeast fields from first yeast (for existing UI)
    if parsed.yeast:
        recipe.yeast_name = parsed.yeast.name
        recipe.yeast_lab = parsed.yeast.lab
        recipe.yeast_product_id = parsed.yeast.product_id
        recipe.yeast_temp_min = parsed.yeast.temp_min_c
        recipe.yeast_temp_max = parsed.yeast.temp_max_c
        recipe.yeast_attenuation = parsed.yeast.attenuation_percent

    db.add(recipe)
    await db.flush()  # Get recipe.id

    # Add fermentables
    for f in parsed.fermentables:
        fermentable = RecipeFermentable(
            recipe_id=recipe.id,
            name=f.name,
            type=f.type,
            amount_kg=f.amount_kg,
            yield_percent=f.yield_percent,
            color_srm=f.color_lovibond,  # BeerXML uses Lovibond, BeerJSON uses SRM (similar scale)
            origin=f.origin,
            supplier=f.supplier,
            notes=f.notes,
            add_after_boil=f.add_after_boil,
            coarse_fine_diff=f.coarse_fine_diff,
            moisture=f.moisture,
            diastatic_power=f.diastatic_power,
            protein=f.protein,
            max_in_batch=f.max_in_batch,
            recommend_mash=f.recommend_mash,
        )
        db.add(fermentable)

    # Add hops
    for h in parsed.hops:
        # Convert BeerXML use/time to BeerJSON timing
        timing = None
        if h.use:
            timing = {
                "use": h.use.lower(),  # BeerJSON uses lowercase
                "duration": {"value": h.time_min or 0, "unit": "min"}
            }

        # Store BeerXML metadata in format_extensions
        format_extensions = {}
        if h.type:
            format_extensions['type'] = h.type
        if h.substitutes:
            format_extensions['substitutes'] = h.substitutes
        if h.hsi is not None:
            format_extensions['hsi'] = h.hsi
        if h.humulene is not None:
            format_extensions['humulene'] = h.humulene
        if h.caryophyllene is not None:
            format_extensions['caryophyllene'] = h.caryophyllene
        if h.cohumulone is not None:
            format_extensions['cohumulone'] = h.cohumulone
        if h.myrcene is not None:
            format_extensions['myrcene'] = h.myrcene
        if h.notes:
            format_extensions['notes'] = h.notes

        hop = RecipeHop(
            recipe_id=recipe.id,
            name=h.name,
            alpha_acid_percent=h.alpha_percent,
            amount_grams=h.amount_kg * 1000 if h.amount_kg else None,
            form=h.form,
            origin=h.origin,
            beta_acid_percent=h.beta_percent,
            timing=timing,
            format_extensions=format_extensions if format_extensions else None,
        )
        db.add(hop)

    # Add cultures (yeasts)
    for y in parsed.yeasts:
        # Determine amount and unit
        amount = None
        amount_unit = None
        if y.amount_l:
            amount = y.amount_l
            amount_unit = "ml"
        elif y.amount_kg:
            amount = y.amount_kg * 1000  # Convert to grams
            amount_unit = "g"

        # Store BeerXML metadata in format_extensions
        format_extensions = {}
        if y.flocculation:
            format_extensions['flocculation'] = y.flocculation
        if y.add_to_secondary is not None:
            format_extensions['add_to_secondary'] = y.add_to_secondary
        if y.best_for:
            format_extensions['best_for'] = y.best_for
        if y.times_cultured is not None:
            format_extensions['times_cultured'] = y.times_cultured
        if y.max_reuse is not None:
            format_extensions['max_reuse'] = y.max_reuse
        if y.notes:
            format_extensions['notes'] = y.notes

        culture = RecipeCulture(
            recipe_id=recipe.id,
            name=y.name,
            producer=y.lab,  # BeerXML "lab" → BeerJSON "producer"
            product_id=y.product_id,
            type=y.type,
            form=y.form,
            attenuation_min_percent=y.attenuation_percent,  # BeerXML has single value, map to min
            attenuation_max_percent=y.attenuation_percent,  # Same for max
            temp_min_c=y.temp_min_c,
            temp_max_c=y.temp_max_c,
            amount=amount,
            amount_unit=amount_unit,
            format_extensions=format_extensions if format_extensions else None,
        )
        db.add(culture)

    # Add miscs
    for m in parsed.miscs:
        misc = RecipeMisc(
            recipe_id=recipe.id,
            name=m.name,
            type=m.type,
            use=m.use,
            time_min=m.time_min,
            amount_kg=m.amount_kg,
            amount_is_weight=m.amount_is_weight,
            use_for=m.use_for,
            notes=m.notes,
        )
        db.add(misc)

    await db.commit()
    return recipe.id
