"""Seeded return resampling without global random state."""
import numpy as np

def resample_paths(values, config):
    source = np.asarray(values, dtype=float)
    rng = np.random.default_rng(config.seed)
    n, sims = len(source), config.simulation_count
    if config.method == "iid_bootstrap":
        return rng.choice(source, size=(sims, n), replace=True)
    if config.method == "path_permutation":
        return rng.permuted(np.tile(source, (sims, 1)), axis=1)
    block = config.block_length
    starts = np.arange(0, n - block + 1)
    pieces = -(-n // block)
    idx = rng.choice(starts, size=(sims, pieces))
    window = (idx[:, :, None] + np.arange(block)).reshape(sims, -1)[:, :n]
    return source[window]
