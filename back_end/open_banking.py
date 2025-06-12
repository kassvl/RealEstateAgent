"""Stub Open Banking affordability calculator. In real life we'd connect via PSD2 APIs.
Here we just accept monthly income & expense arrays and compute disposable income ratio."""
from typing import List


def affordability_score(incomes: List[float], expenses: List[float]) -> float:
    """Return score 0-100 where 100 = very affordable."""
    avg_income = sum(incomes) / len(incomes) if incomes else 0
    avg_expense = sum(expenses) / len(expenses) if expenses else 0
    if avg_income == 0:
        return 0.0
    ratio = (avg_income - avg_expense) / avg_income  # disposable income ratio
    return max(0, min(100, ratio * 100))
