#!/usr/bin/env python3
"""Low-level PowerGraph .mat helpers (MATLAB v7.3 / HDF5)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import numpy as np

# Verified on ieee118/ieee118/raw (Figshare PowerGraph)
CASCADE_VAR_NAMES: dict[str, str] = {
    "blist.mat": "bList",
    "Bf.mat": "B_f_tot",
    "Ef.mat": "E_f_post",
    "Ef_nc.mat": "E_f_kenza",
    "of_bi.mat": "output_features",
    "of_reg.mat": "dns_MW",
    "of_mc.mat": "category",
    "exp.mat": "explainations",
}


def mat_var_name(path: Path) -> str:
    return CASCADE_VAR_NAMES.get(path.name, path.stem)


def _is_v73(path: Path) -> bool:
    import scipy.io

    try:
        scipy.io.loadmat(str(path), squeeze_me=True)
        return False
    except NotImplementedError:
        return True


def _read_v73_dataset(path: Path, key: str) -> np.ndarray:
    import h5py

    with h5py.File(path, "r") as hf:
        if key not in hf:
            keys = [k for k in hf.keys() if not k.startswith("#")]
            if len(keys) != 1:
                raise KeyError(f"{key!r} not in {path.name}; keys={keys}")
            key = keys[0]
        return np.array(hf[key])


def _deref(hf, ref) -> np.ndarray:
    import h5py

    if isinstance(ref, np.ndarray) and ref.shape == ():
        ref = ref[()]
    try:
        return np.array(hf[ref])
    except (TypeError, ValueError, KeyError) as exc:
        raise TypeError(f"Cannot dereference {type(ref)} ({ref!r})") from exc


def is_cell_array(path: Path, key: str | None = None) -> bool:
    """True when variable is a MATLAB cell array (HDF5 object references)."""
    import h5py

    key = key or mat_var_name(path)
    with h5py.File(path, "r") as hf:
        return h5py.check_dtype(ref=hf[key].dtype) is not None


def _cell_dataset(path: Path, key: str):
    import h5py

    with h5py.File(path, "r") as hf:
        if key not in hf:
            keys = [k for k in hf.keys() if not k.startswith("#")]
            if len(keys) != 1:
                raise KeyError(f"{key!r} not in {path.name}; keys={keys}")
            key = keys[0]
        ds = hf[key]
        yield hf, ds


def _cell_count(path: Path, key: str) -> int:
    for _, ds in _cell_dataset(path, key):
        return int(ds.size)
    return 0


def _cell_ref_at(ds, linear_idx: int):
    idx = np.unravel_index(linear_idx, ds.shape)
    return ds[idx]


def iter_cell_samples(path: Path, key: str | None = None) -> Iterator[np.ndarray]:
    """Yield dereferenced elements from a MATLAB v7.3 cell array."""
    key = key or mat_var_name(path)
    for hf, ds in _cell_dataset(path, key):
        for i in range(ds.size):
            yield _deref(hf, _cell_ref_at(ds, i))


def load_cell_samples(
    path: Path,
    key: str | None = None,
    *,
    indices: slice | range | list[int] | np.ndarray | None = None,
    sample_index: slice | range | list[int] | np.ndarray | None = None,
) -> np.ndarray:
    """Load MATLAB cell array into a stacked numpy array."""
    if sample_index is not None:
        indices = sample_index
    key = key or mat_var_name(path)
    for hf, ds in _cell_dataset(path, key):
        n = ds.size
        if indices is None:
            pick = range(n)
        elif isinstance(indices, slice):
            pick = range(*indices.indices(n))
        else:
            pick = indices

        out: list[np.ndarray] = []
        for i in pick:
            out.append(_deref(hf, _cell_ref_at(ds, int(i))))
        if not out:
            return np.empty((0,))
        if out[0].ndim == 0:
            return np.asarray(out)
        try:
            return np.stack(out, axis=0)
        except ValueError:
            raise ValueError(
                f"{path.name}: cell elements have different shapes; "
                "use load_cell_list() instead of load_cell_samples()"
            ) from None
    return np.empty((0,))


def load_cell_list(
    path: Path,
    key: str | None = None,
    *,
    indices: slice | range | list[int] | np.ndarray | None = None,
) -> list[np.ndarray]:
    """Load MATLAB cell array as a Python list (supports variable-shaped cells)."""
    key = key or mat_var_name(path)
    for hf, ds in _cell_dataset(path, key):
        n = ds.size
        if indices is None:
            pick = range(n)
        elif isinstance(indices, slice):
            pick = range(*indices.indices(n))
        else:
            pick = indices
        return [_deref(hf, _cell_ref_at(ds, int(i))) for i in pick]
    return []


def load_mat_array(path: Path, key: str | None = None) -> np.ndarray:
    """Load numeric .mat variable (v5 or v7.3)."""
    key = key or mat_var_name(path)
    if _is_v73(path):
        arr = _read_v73_dataset(path, key)
    else:
        import scipy.io

        data = scipy.io.loadmat(str(path), squeeze_me=True, struct_as_record=False)
        keys = [k for k in data if not k.startswith("__")]
        if key not in keys:
            key = keys[0]
        arr = np.asarray(data[key])
    return arr


def normalize_blist(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=np.float64)
    if arr.shape == (2, 186):
        arr = arr.T
    return arr


def normalize_bus_features(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=np.float64)
    if arr.ndim == 2 and arr.shape == (3, 118):
        return arr.T
    return arr


def normalize_branch_features(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=np.float64)
    if arr.ndim == 2 and arr.shape == (4, 186):
        return arr.T
    return arr


def normalize_labels(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr)
    if arr.ndim == 0:
        return arr.reshape(1)
    return arr.ravel()


def inspect_cell_sample(path: Path, key: str | None = None, index: int = 0) -> tuple[np.ndarray, int]:
    """Return one dereferenced cell and total cell count."""
    key = key or mat_var_name(path)
    if not is_cell_array(path, key):
        arr = normalize_labels(load_mat_array(path, key))
        return arr, int(arr.size)

    n = _cell_count(path, key)
    sample = next(x for i, x in enumerate(iter_cell_samples(path, key)) if i == index)
    return sample, n


def load_labels(
    path: Path,
    key: str | None = None,
    *,
    indices: slice | range | list[int] | np.ndarray | None = None,
) -> np.ndarray:
    """Load label vector from dense array or cell array."""
    key = key or mat_var_name(path)
    if is_cell_array(path, key):
        arr = load_cell_samples(path, key, indices=indices)
    else:
        arr = normalize_labels(load_mat_array(path, key))
        if indices is not None:
            arr = arr[indices]
        return arr
    return normalize_labels(arr)
