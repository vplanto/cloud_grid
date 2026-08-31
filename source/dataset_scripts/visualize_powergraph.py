#!/usr/bin/env python3
"""Згенерувати PNG-діаграми для n01 (розділ про датасет).

    pip install numpy scipy h5py matplotlib
    python source/dataset_scripts/visualize_powergraph.py --data ~/Downloads/dataset

Файли з'являться у docs/assets/powergraph/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_powergraph_cascades import build_topology, load_powergraph_cascades

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "assets" / "powergraph"


def _require_matplotlib():
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit("Потрібен matplotlib: pip install matplotlib") from exc
    return plt


def plot_dns_histogram(of_reg: np.ndarray, out: Path) -> None:
    plt = _require_matplotlib()
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(of_reg, bins=60, color="#38bdf8", edgecolor="#0f172a", linewidth=0.3)
    ax.set_xlabel("dns_MW (частка невиконаного попиту)")
    ax.set_ylabel("кількість зразків")
    ax.set_title("PowerGraph IEEE-118: розподіл DNS (122 500 сценаріїв Cascades)")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def plot_blackout_bar(of_bi: np.ndarray, out: Path) -> None:
    plt = _require_matplotlib()
    labels = ["без блек-ауту (0)", "є DNS (1)"]
    counts = [int(np.sum(of_bi == 0)), int(np.sum(of_bi == 1))]
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.bar(labels, counts, color=["#34d399", "#f87171"])
    ax.set_ylabel("кількість зразків")
    ax.set_title("Бінарні мітки output_features")
    for i, c in enumerate(counts):
        ax.text(i, c, f"{c:,}", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def plot_branch_flow_vs_capacity(pg, sample: int, out: Path) -> None:
    plt = _require_matplotlib()
    topo = build_topology(pg.blist, pg.Ef[sample], pg.Bf[sample])
    flows = [b["flow"] for b in topo["branches"]]
    caps = [b["capacity"] for b in topo["branches"]]
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(caps, np.abs(flows), s=12, alpha=0.6, c="#a78bfa")
    lim = max(max(caps), max(np.abs(flows))) * 1.05
    ax.plot([0, lim], [0, lim], "--", color="#64748b", label="flow = capacity")
    ax.set_xlabel("line rating lr (capacity)")
    ax.set_ylabel("|P_ij| (початковий потік)")
    ax.set_title(f"Зразок s={sample}: навантаження гілок до аварії")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def plot_node_load(pg, sample: int, out: Path) -> None:
    plt = _require_matplotlib()
    loads = pg.Bf[sample, :, 0]
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.bar(np.arange(1, len(loads) + 1), loads, width=1.0, color="#38bdf8")
    ax.set_xlabel("вузол (bus id)")
    ax.set_ylabel("P_net")
    ax.set_title(f"Зразок s={sample}: навантаження вузлів")
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path.home() / "Downloads" / "dataset")
    parser.add_argument("--sample", type=int, default=0)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Завантаження міток (швидко, без Bf/Ef)...")
    pg_labels = load_powergraph_cascades(args.data, load_large=False)
    plot_dns_histogram(pg_labels.of_reg, OUT_DIR / "dns_histogram.png")
    plot_blackout_bar(pg_labels.of_bi, OUT_DIR / "blackout_bar.png")
    print(f"  → {OUT_DIR / 'dns_histogram.png'}")
    print(f"  → {OUT_DIR / 'blackout_bar.png'}")

    print(f"Завантаження одного зразка s={args.sample} для графіків гілок/вузлів...")
    pg = load_powergraph_cascades(args.data, sample_index=slice(args.sample, args.sample + 1))
    plot_branch_flow_vs_capacity(pg, 0, OUT_DIR / "branch_flow_vs_capacity.png")
    plot_node_load(pg, 0, OUT_DIR / "node_loads.png")
    print(f"  → {OUT_DIR / 'branch_flow_vs_capacity.png'}")
    print(f"  → {OUT_DIR / 'node_loads.png'}")
    print("Готово.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
