"""Research-only river bet update using public solver reach and profile counts."""
import numpy as np


def bet_update(prior, targets, probabilities, observed, bet_count):
    """Return normalized posterior, relative likelihood and size evidence weight.

    The combo axis contains only Hero/board-compatible pairs. Zero prior
    entries are retained as zero. Rows are existing opening bet/shove policies.
    """
    prior = np.asarray(prior, dtype=float)
    targets = np.asarray(targets, dtype=float)
    probabilities = np.asarray(probabilities, dtype=float)
    if (prior.ndim != 1 or not np.isfinite(prior).all() or (prior < 0).any()
            or not prior.sum() > 0 or targets.ndim != 1 or not targets.size
            or not np.isfinite(targets).all() or targets[0] <= 0
            or not (np.diff(targets) > 0).all()
            or probabilities.shape != (targets.size, prior.size)
            or not np.isfinite(probabilities).all() or (probabilities < 0).any()
            or (probabilities.sum(axis=0) > 1 + 1e-10).any()
            or not np.isfinite(observed) or not 0 < observed <= targets[-1]
            or type(bet_count) is not int or bet_count < 0):
        raise ValueError("invalid opening-bet inputs")
    prior = prior / prior.sum()
    pooled = probabilities.sum(axis=0)
    pooled_mass = pooled @ prior
    if not pooled_mass:
        return prior, np.ones_like(prior), 0.0
    upper = int(np.searchsorted(targets, observed))
    if upper == 0 or targets[upper] == observed:
        local = probabilities[upper]
    else:
        lo, x, hi = np.log([targets[upper - 1], observed, targets[upper]])
        weight = (x - lo) / (hi - lo)
        local = (1 - weight) * probabilities[upper - 1] + weight * probabilities[upper]
    local_mass = local @ prior
    confidence = bet_count / (bet_count + 20) if local_mass else 0.0
    likelihood = .05 + .95 * (1 - confidence) * pooled / pooled_mass
    if confidence:
        likelihood += .95 * confidence * local / local_mass
    posterior = prior * likelihood
    return posterior / posterior.sum(), likelihood / likelihood.max(), confidence
