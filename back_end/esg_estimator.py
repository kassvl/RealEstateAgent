"""Rudimentary ESG & energy class estimator (stub)."""
import math


def estimate_energy_score(year_built: int | None, heating_type: str | None) -> float:
    """Return energy score 0 (poor) – 100 (excellent). Placeholder linear formula."""
    base = 80 if year_built and year_built >= 2015 else 50 if year_built and year_built >= 2000 else 30
    heating_bonus = 10 if heating_type in {"heat_pump", "district"} else -10 if heating_type == "coal" else 0
    return max(0, min(100, base + heating_bonus))


def estimate_co2_emission(area_sqm: float, energy_score: float) -> float:
    """kg CO2 / m²/year (very rough inverse relation)."""
    return area_sqm * (1 - energy_score / 100) * 5  # arbitrary factor
