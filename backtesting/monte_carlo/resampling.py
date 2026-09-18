"""Seeded return resampling without global random state."""
import numpy as np

def resample_paths(values, config):
    source = np.asarray(values, dtype=float)
    rng = np.random.default_rng(config.seed)
    n, sims = len(source), config.simulation_count
    if config.method == "iid_bootstrap":
        return rng.choice(source, size=(sims, n), replace=True)
    if config.method == "path_permutation":
        return np.stack([rng.permutation(source) for _ in range(sims)])
    block = config.block_length
    starts = np.arange(0, n - block + 1)
    paths = []
    for _ in range(sims):
        pieces = []
        while sum(len(x) for x in pieces) < n:
            start = int(rng.choice(starts))
            pieces.append(source[start:start + block])
        paths.append(np.concatenate(pieces)[:n])
    return np.stack(paths)
