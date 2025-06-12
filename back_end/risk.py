"""Risk utilities for mortgage portfolio (VaR, Expected Loss)."""
import numpy as np
from typing import List


def simulate_portfolio_losses(exposures: List[float], default_probs: List[float], n_sim: int = 10000):
    """Monte Carlo simulation of portfolio losses.

    exposures: principal amounts per loan.
    default_probs: corresponding probability of default per loan.
    returns: np.ndarray of simulated total losses.
    """
    exposures = np.array(exposures)
    default_probs = np.array(default_probs)
    sims = np.random.rand(n_sim, len(exposures)) < default_probs  # default indicator
    losses = (sims * exposures).sum(axis=1)
    return losses


def value_at_risk(losses: np.ndarray, alpha: float = 0.99):
    """Compute historical VaR at level alpha for array of losses."""
    return np.percentile(losses, alpha * 100)


def expected_loss(default_probs: List[float], exposures: List[float]):
    """Expected loss = sum(PD * exposure)."""
    return float((np.array(default_probs) * np.array(exposures)).sum())
