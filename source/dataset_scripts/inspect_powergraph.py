#!/usr/bin/env python3
"""Inspect PowerGraph .mat files (cascades / pf_opf).

Default layout after unpacking Figshare archives on Linux:

    ~/Downloads/dataset/dataset_cascades/ieee118/ieee118/raw/*.mat

Usage:
    python source/dataset_scripts/inspect_powergraph.py
    python source/dataset_scripts/inspect_powergraph.py --data ~/Downloads/dataset
    python source/dataset_scripts/inspect_powergraph.py --cascades ~/Downloads/dataset/dataset_cascades/ieee118/ieee118/raw
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from powergraph_mat import (
    inspect_cell_sample,
    is_cell_array,
    load_mat_array,
    mat_var_name,
    normalize_blist,
)


CASCADE_FILES = [
    "blist.mat",
    "Bf.mat",
    "Ef.mat",
    "Ef_nc.mat",
    "of_bi.mat",
    "of_reg.mat",
    "of_mc.mat",
    "exp.mat",
]

PF_OPF_FILES = [
    "edge_index.mat",
    "edge_attr.mat",
    "X.mat",
    "Y_polar.mat",
    "edge_index_opf.mat",
    "edge_attr_opf.mat",
    "Xopf.mat",
    "Y_polar_opf.mat",
]


def find_raw_dir(base: Path, dataset: str, bus: str) -> Path:
    """Find .../<dataset>/<bus>/.../raw containing blist.mat."""
    root = base / dataset / bus
    candidates = [
        root / bus / "raw",
        root / "raw",
        root,
    ]
    for path in candidates:
        if (path / "blist.mat").exists():
            return path
    raise FileNotFoundError(
        f"blist.mat not found. Tried:\n"
        + "\n".join(f"  - {p}" for p in candidates)
    )


def _mat_keys(data: dict) -> list[str]:
    return [k for k in data if not k.startswith("__")]


def load_mat(path: Path, *, peek: bool = True) -> dict:
    """Load .mat (v5/v7) or inspect v7.3 HDF5 without reading huge arrays."""
    import scipy.io

    try:
        return scipy.io.loadmat(str(path), squeeze_me=True, struct_as_record=False)
    except NotImplementedError:
        import h5py

        out: dict = {}
        with h5py.File(path, "r") as hf:
            for key in hf.keys():
                if key.startswith("#"):
                    continue
                ds = hf[key]
                if not isinstance(ds, h5py.Dataset):
                    out[key] = {"type": type(ds).__name__}
                    continue
                info = {"shape": tuple(int(x) for x in ds.shape), "dtype": str(ds.dtype), "format": "v7.3"}
                if peek and is_cell_array(path, key):
                    sample, n = inspect_cell_sample(path, key, index=0)
                    info["n_cells"] = n
                    info["cell0_shape"] = tuple(int(x) for x in sample.shape)
                    info["cell0_dtype"] = str(sample.dtype)
                elif peek and ds.size and ds.size <= 32:
                    info["values"] = np.array(ds)
                elif peek and ds.ndim == 1 and ds.size <= 16:
                    info["head"] = np.array(ds[:8])
                out[key] = info
        return out


def describe_value(name: str, value, indent: str = "  ") -> list[str]:
    lines: list[str] = []
    if isinstance(value, dict) and value.get("format") == "v7.3":
        lines.append(f"{indent}{name}: v7.3 shape={value['shape']} dtype={value['dtype']}")
        if "n_cells" in value:
            lines.append(
                f"{indent}  cells={value['n_cells']} "
                f"cell0 shape={value.get('cell0_shape')} dtype={value.get('cell0_dtype')}"
            )
        if "values" in value:
            lines.append(f"{indent}  values={value['values']}")
        if "head" in value:
            lines.append(f"{indent}  head={value['head']}")
        return lines

    if isinstance(value, np.ndarray):
        lines.append(f"{indent}{name}: shape={value.shape} dtype={value.dtype}")
        if value.size <= 20:
            lines.append(f"{indent}  values={value}")
        elif value.ndim == 1:
            lines.append(
                f"{indent}  min={value.min()} max={value.max()} "
                f"mean={value.mean():.6g} head={value[:8]}"
            )
        elif value.ndim == 2 and value.shape[0] <= 4:
            for i, row in enumerate(value):
                lines.append(f"{indent}  row{i}={row}")
        elif value.ndim == 2:
            lines.append(f"{indent}  row0={value[0]} row1={value[1]}")
        elif value.ndim == 3:
            lines.append(
                f"{indent}  sample0 shape={value[0].shape} "
                f"bus0={value[0, 0]} branch0={value[0, 0]}"
            )
        return lines

    lines.append(f"{indent}{name}: type={type(value).__name__} value={value!r}")
    return lines


def inspect_file(path: Path) -> None:
    size_mb = path.stat().st_size / 1e6
    print(f"\n=== {path.name} ({size_mb:.2f} MB) ===")
    if not path.exists():
        print("  MISSING")
        return

    try:
        data = load_mat(path)
    except Exception as exc:
        print(f"  load error: {exc}")
        return

    keys = _mat_keys(data)
    print(f"  keys: {keys}")
    for key in keys:
        for line in describe_value(key, data[key]):
            print(line)


def quick_summary(cascades_raw: Path) -> None:
    """Minimal check: file → MATLAB variable → shape."""
    print("\n--- quick summary ---")
    for fname in ["blist.mat", "Bf.mat", "Ef.mat", "of_reg.mat"]:
        path = cascades_raw / fname
        if not path.exists():
            print(fname, "MISSING")
            continue
        var = mat_var_name(path)
        try:
            if is_cell_array(path, var):
                sample, n = inspect_cell_sample(path, var, index=0)
                print(f"{fname} [{var!r}] cells={n} cell0={sample.shape} {sample.dtype}")
            else:
                arr = load_mat_array(path, var)
                if fname == "blist.mat":
                    arr = normalize_blist(arr)
                print(f"{fname} [{var!r}] {arr.shape} {arr.dtype}")
        except Exception as exc:
            print(fname, "ERROR", exc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        type=Path,
        default=Path.home() / "Downloads" / "dataset",
        help="Root with dataset_cascades/ and dataset_pf_opf/ (default: ~/Downloads/dataset)",
    )
    parser.add_argument("--cascades", type=Path, help="Override cascades raw directory")
    parser.add_argument("--pf-opf", type=Path, help="Override pf_opf raw directory")
    parser.add_argument("--bus", default="ieee118", help="Bus system folder name (default: ieee118)")
    parser.add_argument("--quick", action="store_true", help="Only print keys/shapes for 4 main files")
    args = parser.parse_args()

    try:
        cascades_raw = args.cascades or find_raw_dir(args.data, "dataset_cascades", args.bus)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"cascades raw: {cascades_raw.resolve()}")

    if args.quick:
        quick_summary(cascades_raw)
        return 0

    for fname in CASCADE_FILES:
        inspect_file(cascades_raw / fname)

    pf_root = args.pf_opf
    if pf_root is None:
        try:
            pf_root = find_raw_dir(args.data, "dataset_pf_opf", args.bus)
        except FileNotFoundError:
            pf_root = None

    if pf_root is not None:
        print(f"\npf_opf raw: {pf_root.resolve()}")
        for fname in PF_OPF_FILES:
            inspect_file(pf_root / fname)

    quick_summary(cascades_raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
