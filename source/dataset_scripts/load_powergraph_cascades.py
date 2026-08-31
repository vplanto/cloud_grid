#!/usr/bin/env python3
"""Load PowerGraph cascades for IEEE-118 (and other bus systems).

Figshare layout:

    ~/Downloads/dataset/dataset_cascades/ieee118/ieee118/raw/

All ieee118 cascade files are MATLAB v7.3. Feature arrays are cell arrays
with N=122500 samples (verified locally).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from powergraph_mat import (
    load_cell_list,
    load_cell_samples,
    load_labels,
    load_mat_array,
    mat_var_name,
    normalize_blist,
    normalize_branch_features,
    normalize_bus_features,
)


@dataclass(frozen=True)
class PowerGraphCascades:
    blist: np.ndarray  # (n_branches, 2)
    Bf: np.ndarray  # (n_samples, n_buses, 3)
    Ef: np.ndarray  # (n_samples, n_branches, 4)
    of_bi: np.ndarray  # (n_samples,)
    of_reg: np.ndarray  # (n_samples,) DNS in MW
    of_mc: np.ndarray | None = None
    exp: list[np.ndarray] | None = None
    raw_dir: Path | None = None

    @property
    def n_samples(self) -> int:
        return int(self.of_reg.shape[0])

    @property
    def n_buses(self) -> int:
        return int(self.blist.shape[0] and (self.Bf.shape[1] if self.Bf.size else 118))

    @property
    def n_branches(self) -> int:
        return int(self.blist.shape[0])


def find_cascades_raw(data_root: Path, bus: str = "ieee118") -> Path:
    root = data_root / "dataset_cascades" / bus
    for candidate in (root / bus / "raw", root / "raw", root):
        if (candidate / "blist.mat").exists():
            return candidate
    raise FileNotFoundError(f"PowerGraph cascades not found under {root}")


def _load_labels(path: Path, sample_index=None) -> np.ndarray:
    return load_labels(path, indices=sample_index)


def load_powergraph_cascades(
    data_dir: Path | str,
    *,
    bus: str = "ieee118",
    load_large: bool = True,
    load_exp: bool = False,
    sample_index: slice | range | list[int] | np.ndarray | None = None,
) -> PowerGraphCascades:
    path = Path(data_dir)
    raw = path if (path / "blist.mat").exists() else find_cascades_raw(path, bus)

    blist = normalize_blist(load_mat_array(raw / "blist.mat"))
    of_reg = _load_labels(raw / "of_reg.mat", sample_index)
    of_bi = _load_labels(raw / "of_bi.mat", sample_index)

    of_mc = None
    if (raw / "of_mc.mat").exists():
        of_mc = _load_labels(raw / "of_mc.mat", sample_index)

    exp = None
    if load_exp and (raw / "exp.mat").exists():
        exp = load_cell_list(raw / "exp.mat", indices=sample_index)

    if load_large:
        Bf_raw = load_cell_samples(raw / "Bf.mat", indices=sample_index)
        Ef_raw = load_cell_samples(raw / "Ef.mat", indices=sample_index)
        Bf = np.stack([normalize_bus_features(x) for x in Bf_raw], axis=0)
        Ef = np.stack([normalize_branch_features(x) for x in Ef_raw], axis=0)
    else:
        Bf = np.empty((0, 0, 0))
        Ef = np.empty((0, 0, 0))

    return PowerGraphCascades(
        blist=blist,
        Bf=Bf,
        Ef=Ef,
        of_bi=of_bi,
        of_reg=of_reg,
        of_mc=of_mc,
        exp=exp,
        raw_dir=raw,
    )


def build_topology(blist: np.ndarray, branch_features: np.ndarray, bus_features: np.ndarray) -> dict:
    n_branches = blist.shape[0]
    branches = []
    for i in range(n_branches):
        from_bus, to_bus = int(blist[i, 0]), int(blist[i, 1])
        p_ij, q_ij, x_ij, lr_ij = (float(x) for x in branch_features[i])
        branches.append(
            {
                "id": i,
                "from_bus": from_bus,
                "to_bus": to_bus,
                "flow": p_ij,
                "capacity": lr_ij,
                "active": True,
            }
        )

    buses = []
    for j in range(bus_features.shape[0]):
        p_net, s_net, v = (float(x) for x in bus_features[j])
        buses.append({"id": j + 1, "load": p_net, "voltage": v})

    return {"buses": buses, "branches": branches}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path.home() / "Downloads" / "dataset")
    parser.add_argument("--bus", default="ieee118")
    parser.add_argument("--no-large", action="store_true", help="Skip Bf/Ef (fast)")
    parser.add_argument("--with-exp", action="store_true", help="Load exp.mat (XAI, variable shape)")
    parser.add_argument("--samples", default=None, help="Slice, e.g. 0:10 or 0:1000")
    args = parser.parse_args()

    sample_index = None
    if args.samples:
        parts = [int(x) if x else None for x in args.samples.split(":")]
        while len(parts) < 3:
            parts.append(None)
        sample_index = slice(*parts)

    pg = load_powergraph_cascades(
        args.data,
        bus=args.bus,
        load_large=not args.no_large,
        load_exp=args.with_exp,
        sample_index=sample_index,
    )
    print(f"raw_dir: {pg.raw_dir}")
    print(f"blist: {pg.blist.shape}")
    print(f"of_reg (dns_MW): {pg.of_reg.shape} min={pg.of_reg.min():.4g} max={pg.of_reg.max():.4g}")
    print(f"of_bi (output_features): {pg.of_bi.shape} unique={np.unique(pg.of_bi)[:8]}")
    if pg.n_samples and pg.Bf.size:
        print(f"Bf: {pg.Bf.shape}  Ef: {pg.Ef.shape}")
        topo = build_topology(pg.blist, pg.Ef[0], pg.Bf[0])
        print(f"buses={len(topo['buses'])} branches={len(topo['branches'])}")
