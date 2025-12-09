"""Recipe validation business logic."""
from typing import Optional
from fastapi import HTTPException


def validate_recipe_constraints(
    og: Optional[float],
    fg: Optional[float],
    batch_size_liters: Optional[float],
    abv: Optional[float],
) -> None:
    """Validate recipe business logic constraints.

    Args:
        og: Original gravity (e.g., 1.050)
        fg: Final gravity (e.g., 1.010)
        batch_size_liters: Batch size in liters
        abv: Alcohol by volume percentage

    Raises:
        HTTPException: If validation fails with 400 status and descriptive message
    """
    # Only validate OG > FG if both values are provided
    if og is not None and fg is not None and og <= fg:
        raise HTTPException(
            status_code=400,
            detail="Original gravity must be greater than final gravity"
        )

    if batch_size_liters is not None and batch_size_liters <= 0:
        raise HTTPException(
            status_code=400,
            detail="Batch size must be greater than zero"
        )

    if abv is not None and (abv < 0 or abv > 20):
        raise HTTPException(
            status_code=400,
            detail="ABV must be between 0% and 20%"
        )
