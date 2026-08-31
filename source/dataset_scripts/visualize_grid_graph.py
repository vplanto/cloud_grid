#!/usr/bin/env python3
"""Топологічний граф IEEE-118 з PowerGraph → PNG.

    pip install numpy scipy h5py matplotlib networkx
    python source/dataset_scripts/visualize_grid_graph.py --data ~/Downloads/dataset --samples 0,1,2
    python source/dataset_scripts/visualize_grid_graph.py --data ~/Downloads/dataset --sample 0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_powergraph_cascades import find_cascades_raw, load_powergraph_cascades
from powergraph_mat import load_mat_array, normalize_blist

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = REPO_ROOT / "docs" / "assets" / "powergraph"
DEFAULT_OUT = OUT_DIR / "ieee118_topology.png"


def _require_deps():
    try:
        import matplotlib.pyplot as plt
        import networkx as nx
    except ImportError as exc:
        raise SystemExit("Потрібно: pip install matplotlib networkx") from exc
    return plt, nx


def build_networkx_graph(blist: np.ndarray, nx):
    graph = nx.Graph()
    for i in range(blist.shape[0]):
        u, v = int(blist[i, 0]), int(blist[i, 1])
        graph.add_edge(u, v, branch_id=i)
    return graph


def compute_layout(blist: np.ndarray, layout: str):
    _, nx = _require_deps()
    graph = build_networkx_graph(blist, nx)
    if layout == "spring":
        return nx.spring_layout(graph, seed=42, k=2.0 / np.sqrt(graph.number_of_nodes()))
    return nx.kamada_kawai_layout(graph)


def node_values(graph, bus_features: np.ndarray | None) -> list[float]:
    if bus_features is not None:
        out = []
        for bus_id in graph.nodes:
            idx = bus_id - 1
            if 0 <= idx < bus_features.shape[0]:
                out.append(float(abs(bus_features[idx, 0])))
            else:
                out.append(0.0)
        return out
    return [float(graph.degree(n)) for n in graph.nodes]


def edge_values(blist: np.ndarray, branch_features: np.ndarray | None, graph) -> list[float]:
    if branch_features is not None:
        util = []
        for i in range(blist.shape[0]):
            flow = abs(float(branch_features[i, 0]))
            cap = float(branch_features[i, 3])
            util.append(flow / cap if cap > 0 else 0.0)
        return [util[data["branch_id"]] for _, _, data in graph.edges(data=True)]
    return [1.0] * graph.number_of_edges()


def plot_graph(
    blist: np.ndarray,
    *,
    bus_features: np.ndarray | None = None,
    branch_features: np.ndarray | None = None,
    layout: str = "kamada_kawai",
    pos=None,
    with_labels: bool = False,
    title: str | None = None,
    out: Path,
    dpi: int = 160,
) -> None:
    plt, nx = _require_deps()

    graph = build_networkx_graph(blist, nx)
    if pos is None:
        pos = compute_layout(blist, layout)

    colored_by_load = bus_features is not None
    node_colors = node_values(graph, bus_features)
    edge_vals = edge_values(blist, branch_features, graph)
    has_edge_metric = branch_features is not None

    fig, ax = plt.subplots(figsize=(12, 10))

    if has_edge_metric:
        edges = nx.draw_networkx_edges(
            graph,
            pos,
            edge_color=edge_vals,
            edge_cmap=plt.cm.plasma,
            edge_vmin=min(edge_vals),
            edge_vmax=max(edge_vals) or 1.0,
            width=1.4,
            alpha=0.85,
            ax=ax,
        )
    else:
        edges = nx.draw_networkx_edges(
            graph,
            pos,
            edge_color="#475569",
            width=1.2,
            alpha=0.75,
            ax=ax,
        )

    nodes = nx.draw_networkx_nodes(
        graph,
        pos,
        node_color=node_colors,
        cmap="YlOrRd" if colored_by_load else "viridis",
        node_size=70,
        linewidths=0.4,
        edgecolors="#0f172a",
        alpha=0.95,
        ax=ax,
    )

    if with_labels:
        nx.draw_networkx_labels(graph, pos, font_size=5, font_color="#0f172a", ax=ax)

    n_buses = graph.number_of_nodes()
    n_branches = graph.number_of_edges()
    main_title = title or f"IEEE-118 ({n_buses} вузлів, {n_branches} гілок)"
    ax.set_title(
        f"{main_title}\n(топологічна схема — вузли розставлені алгоритмом, це не географія)",
        fontsize=11,
        pad=12,
    )
    ax.axis("off")

    fig.subplots_adjust(left=0.02, right=0.98, top=0.90, bottom=0.24)

    if nodes is not None and len(set(node_colors)) > 1:
        cax_n = fig.add_axes([0.10, 0.15, 0.80, 0.022])
        cbar_n = fig.colorbar(nodes, cax=cax_n, orientation="horizontal")
        node_lbl = (
            "Навантаження вузла — скільки енергії споживає підстанція або район"
            if colored_by_load
            else "Ступінь вузла — скільки ліній до нього підключено"
        )
        cbar_n.ax.set_title(node_lbl, fontsize=9, pad=8)
        cbar_n.ax.tick_params(labelsize=8)

    if has_edge_metric and edges is not None and len(set(edge_vals)) > 1:
        cax_e = fig.add_axes([0.10, 0.05, 0.80, 0.022])
        cbar_e = fig.colorbar(edges, cax=cax_e, orientation="horizontal")
        cbar_e.ax.set_title(
            "Завантаженість лінії — частка допустимого струму; ближче до 1 — вищий ризик перевантаження",
            fontsize=9,
            pad=8,
        )
        cbar_e.ax.tick_params(labelsize=8)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi, facecolor="white")
    plt.close(fig)


def _parse_sample_list(samples: str | None, sample: int) -> list[int]:
    if samples:
        return [int(x.strip()) for x in samples.split(",") if x.strip()]
    if sample < 0:
        return []
    return [sample]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path.home() / "Downloads" / "dataset")
    parser.add_argument("--bus", default="ieee118")
    parser.add_argument("--sample", type=int, default=0, help="Один індекс s (-1 = лише топологія)")
    parser.add_argument(
        "--samples",
        default=None,
        help="Кілька сценаріїв через кому, напр. 0,1,2 → три PNG",
    )
    parser.add_argument("--layout", choices=("kamada_kawai", "spring"), default="kamada_kawai")
    parser.add_argument("--labels", action="store_true", help="Підписати номери вузлів")
    parser.add_argument("-o", "--out", type=Path, default=None, help="Файл або тека для кількох сценаріїв")
    parser.add_argument("--dpi", type=int, default=160)
    args = parser.parse_args()

    indices = _parse_sample_list(args.samples, args.sample)

    if not indices:
        raw = find_cascades_raw(args.data, args.bus)
        blist = normalize_blist(load_mat_array(raw / "blist.mat"))
        out = args.out or DEFAULT_OUT
        pos = compute_layout(blist, args.layout)
        plot_graph(
            blist,
            bus_features=None,
            branch_features=None,
            layout=args.layout,
            pos=pos,
            with_labels=args.labels,
            title="IEEE-118 (тільки топологія bList)",
            out=out,
            dpi=args.dpi,
        )
        print(f"Збережено: {out.resolve()}")
        return 0

    lo, hi = min(indices), max(indices) + 1
    pg = load_powergraph_cascades(
        args.data,
        bus=args.bus,
        sample_index=slice(lo, hi),
    )
    pos = compute_layout(pg.blist, args.layout)

    out_dir = OUT_DIR if args.out is None else (args.out if args.out.is_dir() else args.out.parent)
    out_dir.mkdir(parents=True, exist_ok=True)

    for s in indices:
        local_i = s - lo
        if local_i < 0 or local_i >= pg.n_samples:
            print(f"Пропущено s={s}: немає в завантаженому діапазоні [{lo}, {hi})")
            continue

        if args.out and len(indices) == 1 and not args.out.is_dir():
            out_path = args.out
        else:
            out_path = out_dir / f"ieee118_scenario_{s + 1:02d}.png"

        bus_f = pg.Bf[local_i] if pg.Bf.size else None
        branch_f = pg.Ef[local_i] if pg.Ef.size else None
        plot_graph(
            pg.blist,
            bus_features=bus_f,
            branch_features=branch_f,
            layout=args.layout,
            pos=pos,
            with_labels=args.labels,
            title=f"IEEE-118 (сценарій {s + 1} з 122 500)",
            out=out_path,
            dpi=args.dpi,
        )
        print(f"Збережено: {out_path.resolve()}")

    n_bus = len({int(x) for x in pg.blist.ravel()})
    print(f"  вузлів: {n_bus}, гілок: {pg.blist.shape[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
