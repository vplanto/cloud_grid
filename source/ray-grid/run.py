#!/usr/bin/env python3
"""
Ray Grid cluster helper for Practice 2.

Local smoke test (fix errors BEFORE the real cluster):
  python run.py stop
  python run.py local

3-node lab (after local is green):
  Node 1 (head):   python run.py head
  Node 2/3:        python run.py client --head <HEAD_IP>
  Node 1 (load):   python run.py load --preset lab --steps 30 --wait-nodes 3
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PORT = 6379


def _ensure_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def detect_lan_ip() -> str:
    """Best-effort LAN IP for multi-interface laptops."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def run_cmd(cmd, check=True):
    print("$", " ".join(cmd))
    return subprocess.run(cmd, check=check)


def _is_loopback(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


def cmd_head(args):
    lan_ip = args.node_ip or detect_lan_ip()
    cmd = [
        "ray",
        "start",
        "--head",
        "--disable-usage-stats",
        f"--port={args.port}",
        f"--node-ip-address={lan_ip}",
    ]
    if args.num_cpus:
        cmd.append(f"--num-cpus={args.num_cpus}")

    run_cmd(cmd)
    print()
    print("=" * 60)
    print(f"Ray HEAD ready at {lan_ip}:{args.port}")
    print("=" * 60)
    print("On worker machines (2 devices):")
    print(f"  python run.py client --head {lan_ip} --port {args.port}")
    print()
    print("When workers are connected, check:")
    print("  python run.py status")
    print()
    print("Run benchmark from THIS machine:")
    print(f"  python run.py load --preset lab --steps {args.steps}")
    print("=" * 60)


def cmd_client(args):
    local_ip = detect_lan_ip()
    if _is_loopback(args.head):
        print(
            "ERROR: --head 127.0.0.1 / localhost is not a separate worker.\n"
            f"       On another PC run: python run.py client --head {local_ip} --port {args.port}",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.head == local_ip and not args.force:
        print(
            "ERROR: --head is THIS machine's LAN IP — client must run on another PC.\n"
            f"       You are on {local_ip}; head is already here.\n"
            "       For lecture: open a terminal on Windows or Debian and run client there.\n"
            "       For fake 2-node test on one laptop: python run.py client --head ... --force",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.head == local_ip and args.force:
        print(
            "WARNING: --force — second Ray node on the SAME machine (demo only, not real Grid).",
            file=sys.stderr,
        )

    address = f"{args.head}:{args.port}"
    cmd = ["ray", "start", f"--address={address}", "--disable-usage-stats"]
    if args.num_cpus:
        cmd.append(f"--num-cpus={args.num_cpus}")

    run_cmd(cmd)
    print()
    print("=" * 60)
    print(f"Joined Ray cluster at {address}")
    print("Worker is running in background (ray daemon).")
    print("Keep this machine online during the benchmark.")
    print("To detach from cluster later: python run.py stop")
    print("=" * 60)

    if args.watch:
        print("Watching cluster status (Ctrl+C to exit watch only)...")
        try:
            while True:
                subprocess.run(["ray", "status"], check=False)
                time.sleep(args.watch_interval)
        except KeyboardInterrupt:
            print("Stopped status watch.")


def cmd_status(_args):
    run_cmd(["ray", "status"], check=False)


def cmd_stop(_args):
    run_cmd(["ray", "stop"])


def wait_for_cluster_nodes(min_nodes, timeout_sec, head_ip=None):
    import ray

    ray.init(address="auto", ignore_reinit_error=True)
    head_ip = head_ip or detect_lan_ip()
    workers_needed = max(0, min_nodes - 1)
    deadline = time.time() + timeout_sec
    hint_printed = False

    print()
    print(f"Очікую {min_nodes} вузл(и) в кластері (head + {workers_needed} worker(s)).")
    print(f"Зараз підключений лише head на цій машині — це нормально на старті.")
    if workers_needed:
        print()
        print("На ІНШИХ комп'ютерах (Windows / Debian) у НОВОМУ терміналі:")
        print(f"  python run.py client --head {head_ip}")
        print()
        print(
            f"Workers can connect WHILE this waits — load starts after {min_nodes}/{min_nodes} nodes."
        )
        print("Single-machine test: omit --wait-nodes or run: python run.py local")
        print()

    while time.time() < deadline:
        alive = [n for n in ray.nodes() if n.get("Alive")]
        if len(alive) >= min_nodes:
            cpus = int(ray.cluster_resources().get("CPU", 0))
            print(f"Cluster ready: {len(alive)} node(s), {cpus} CPU(s)")
            return
        if not hint_printed and len(alive) < min_nodes:
            hint_printed = True
        print(
            f"Waiting for nodes... {len(alive)}/{min_nodes} "
            f"(потрібно ще {min_nodes - len(alive)}; Ctrl+C — скасувати)"
        )
        time.sleep(2)
    raise TimeoutError(
        f"Only {len([n for n in ray.nodes() if n.get('Alive')])} node(s) after {timeout_sec}s; "
        f"expected at least {min_nodes}. Workers не підключились — перевір client на інших ПК."
    )


def _normalize_run_record(data: dict) -> dict:
    if "runs" in data and isinstance(data["runs"], dict):
        return data["runs"]
    return data


def cmd_report(args):
    import json

    with open(args.baseline, encoding="utf-8") as f:
        baseline = _normalize_run_record(json.load(f))
    with open(args.candidate, encoding="utf-8") as f:
        candidate = _normalize_run_record(json.load(f))

    def row(label, rec):
        m = rec.get("metrics", {})
        return {
            "label": label,
            "arch": rec.get("architecture", "?"),
            "backend": rec.get("backend", "—"),
            "fast": rec.get("initial_fast"),
            "slow": rec.get("initial_slow"),
            "workers": rec.get("cpu_workers"),
            "steps": rec.get("total_steps_executed"),
            "status": rec.get("final_status"),
            "total_s": m.get("total_execution_time_sec"),
            "avg_ms": m.get("avg_step_time_ms"),
            "throughput": m.get("throughput_particles_per_sec"),
        }

    a = row(args.baseline_label, baseline)
    b = row(args.candidate_label, candidate)
    same_load = a["fast"] == b["fast"] and a["slow"] == b["slow"]

    if args.demo:
        cluster = candidate.get("cluster") or {}
        nodes = cluster.get("nodes", "?")
        cpus = cluster.get("cpus", "?")
        preset = candidate.get("preset", "?")

        lines = [
            "",
            "=" * 72,
            "  DEMO: Local PC (stage 1)  ->  Ray Grid (stage 2)",
            "=" * 72,
            "",
            "STAGE 1 -- one computer, batch on multiprocessing.Pool",
            f"  JSON:   {args.baseline}",
            "  Code:   source/mimd-pc/app.py  (practice 1)",
            f"  Hardware: 1 node, {a['workers']} local CPU workers",
            f"  Load:   {a['fast']:,} fast + {a['slow']:,} slow neutrons",
            "",
            "STAGE 2 -- Ray cluster, chunks across nodes (no Docker)",
            f"  JSON:   {args.candidate}",
            "  Code:   source/ray-grid/run.py load",
            f"  Cluster: {nodes} node(s), {cpus} CPUs total (backend={b['backend']})",
            f"  Load:   {b['fast']:,} fast + {b['slow']:,} slow (preset={preset})",
            "",
            "-" * 72,
            f"{'Metric':<28} {'Local (p01)':>18} {'Grid (p02)':>18}",
            "-" * 72,
            f"{'Architecture':<28} {a['arch']:>18} {b['arch']:>18}",
            f"{'Simulation steps':<28} {a['steps']:>18} {b['steps']:>18}",
            f"{'Final status':<28} {a['status']:>18} {b['status']:>18}",
            f"{'Total time, s':<28} {a['total_s']:>18} {b['total_s']:>18}",
            f"{'Avg step, ms':<28} {a['avg_ms']:>18} {b['avg_ms']:>18}",
            f"{'Throughput, parts/s':<28} {a['throughput']:>18} {b['throughput']:>18}",
            "-" * 72,
        ]
        if a["total_s"] and b["total_s"]:
            time_ratio = a["total_s"] / b["total_s"]
            lines.append(f"  Local wall-clock longer: {time_ratio:.1f}x  (different load!)")
        if a["throughput"] and b["throughput"]:
            tp_ratio = b["throughput"] / a["throughput"]
            lines.append(f"  Grid / local throughput: {tp_ratio:.2f}x")
        lines.extend(
            [
                "",
                "SAY ON LECTURE (honest):",
                "  * Illustrates the PATH: one PC -> distributed batch, not a fair bake-off.",
            ]
        )
        if not same_load:
            lines.append(
                "  * Presets DIFFER: p01 heavier (control), p02 lighter (lab). "
                "Time/throughput are not 1:1 comparable."
            )
        lines.extend(
            [
                "  * Grid uses cluster CPUs; local uses one laptop's cores only.",
                "  * Network + chunk serialization = cost of distribution (real 3 PCs on lab day).",
                "  * Docker (stage 3) fixes 'works on my laptop' dependency pain.",
                "=" * 72,
                "",
            ]
        )
        text = "\n".join(lines)
        print(text)

        if args.demo_file:
            out = Path(args.demo_file)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            print(f"Saved copy: {out}")
        return

    print("=" * 72)
    print(" Benchmark comparison")
    print("=" * 72)
    print(f"{'':18} {'A: ' + a['label']:^24} {'B: ' + b['label']:^24}")
    print("-" * 72)
    for key, title in [
        ("arch", "Architecture"),
        ("backend", "Backend"),
        ("fast", "Fast neutrons"),
        ("slow", "Slow neutrons"),
        ("workers", "Workers"),
        ("steps", "Steps executed"),
        ("status", "Final status"),
        ("total_s", "Total time (s)"),
        ("avg_ms", "Avg step (ms)"),
        ("throughput", "Throughput (/s)"),
    ]:
        print(f"{title:18} {str(a[key]):^24} {str(b[key]):^24}")

    if a["throughput"] and b["throughput"]:
        ratio = b["throughput"] / a["throughput"]
        print("-" * 72)
        print(f"B vs A throughput: {ratio:.2f}x")
    print("=" * 72)

    if not same_load:
        print("NOTE: presets differ — compare throughput only after matching --preset control.")


def cmd_local(args):
    """
    Smoke test on ONE machine — no workers, no LAN.
    Order: pool → numpy → ray (head only, 1 node).
    Run this before head + client on real machines.
    """
    sys.path.insert(0, str(SCRIPT_DIR))
    from engine import PRESETS, build_params_from_preset, run_headless_benchmark

    params = build_params_from_preset(args.preset, num_workers=args.workers)
    out = str(SCRIPT_DIR / "benchmark_results_local_smoke.json")

    print("=" * 60)
    print(" LOCAL SMOKE TEST — one machine, no workers")
    print(" Fix errors here BEFORE: head + client on other PCs")
    print("=" * 60)
    print(f"Preset: {args.preset} — {PRESETS[args.preset]['description']}")
    print(f"Steps per backend: {args.steps}")
    print()

    backends = ["pool", "numpy"]
    if not args.skip_ray:
        backends.append("ray")

    for idx, backend in enumerate(backends):
        if backend == "ray":
            print("--- Starting Ray HEAD (single node, no workers) ---")
            lan_ip = detect_lan_ip()
            head_cmd = [
                "ray",
                "start",
                "--head",
                "--disable-usage-stats",
                f"--port={DEFAULT_PORT}",
                f"--node-ip-address={lan_ip}",
            ]
            run_cmd(head_cmd, check=False)
            subprocess.run(["ray", "status"], check=False)
            print()

        print(f"=== [{idx + 1}/{len(backends)}] backend={backend} ===")
        run_headless_benchmark(
            params=params,
            max_steps=args.steps,
            backend=backend,
            output_file=out if backend == backends[-1] else out + ".tmp",
            compare=False,
        )
        print()

    print("=" * 60)
    print(" LOCAL OK — next on the lecture network:")
    print("   1. python run.py stop")
    print("   2. python run.py head")
    print(f"   3. on 2 other machines: python run.py client --head {detect_lan_ip()}")
    print("   4. python run.py load --preset lab --steps 30 --wait-nodes 3")
    print("=" * 60)


def cmd_load(args):
    sys.path.insert(0, str(SCRIPT_DIR))
    from engine import PRESETS, build_params_from_preset, run_headless_benchmark

    if args.wait_nodes > 0:
        wait_for_cluster_nodes(args.wait_nodes, args.wait_timeout, head_ip=detect_lan_ip())

    params = build_params_from_preset(args.preset, num_workers=args.workers)
    if args.fuel is not None:
        params["fuel_mass"] = args.fuel
    if args.fast is not None:
        params["n_fast"] = args.fast
    if args.slow is not None:
        params["n_slow"] = args.slow

    preset_info = PRESETS[args.preset]
    print(f"Preset '{args.preset}': {preset_info['description']}")
    workers_hint = params["num_workers"] if params["num_workers"] is not None else "auto"
    print(
        f"Particles: fast={params['n_fast']:,}, slow={params['n_slow']:,}, "
        f"workers={workers_hint}"
    )

    run_headless_benchmark(
        params=params,
        max_steps=args.steps,
        backend=args.backend,
        output_file=args.out,
        compare=args.compare,
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description="Ray Grid Practice 2 — cluster setup and Monte Carlo load"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    head = sub.add_parser("head", help="Start Ray head node on this machine")
    head.add_argument("--port", type=int, default=DEFAULT_PORT)
    head.add_argument("--node-ip", type=str, default=None, help="LAN IP advertised to workers")
    head.add_argument("--num-cpus", type=int, default=None, help="Limit CPUs on head node")
    head.add_argument("--steps", type=int, default=30, help="Hint for suggested load command")
    head.set_defaults(func=cmd_head)

    client = sub.add_parser("client", help="Join cluster as worker")
    client.add_argument("--head", required=True, help="Head node LAN IP")
    client.add_argument("--port", type=int, default=DEFAULT_PORT)
    client.add_argument("--num-cpus", type=int, default=None, help="Limit CPUs on this worker")
    client.add_argument("--watch", action="store_true", help="Poll ray status until Ctrl+C")
    client.add_argument("--watch-interval", type=float, default=5.0)
    client.add_argument(
        "--force",
        action="store_true",
        help="Allow client on same machine as head (fake cluster, not for lecture)",
    )
    client.set_defaults(func=cmd_client)

    status = sub.add_parser("status", help="Show ray cluster status")
    status.set_defaults(func=cmd_status)

    stop = sub.add_parser("stop", help="Stop local Ray node")
    stop.set_defaults(func=cmd_stop)

    local = sub.add_parser(
        "local",
        help="Smoke test on one machine (pool→numpy→ray) before real cluster",
    )
    local.add_argument("--preset", choices=["lab", "control", "extinction", "explosion"], default="lab")
    local.add_argument("--steps", type=int, default=3, help="Short run per backend (default: 3)")
    local.add_argument("--workers", type=int, default=2, help="Workers for pool/numpy (default: 2)")
    local.add_argument("--skip-ray", action="store_true", help="Only pool+numpy, skip Ray")
    local.set_defaults(func=cmd_local)

    report = sub.add_parser("report", help="Compare two benchmark JSON files")
    report.add_argument(
        "--baseline",
        type=str,
        default=str(SCRIPT_DIR.parent / "mimd-pc" / "benchmark_results_mimd_pc.json"),
        help="Reference JSON (default: p01 mimd-pc)",
    )
    report.add_argument(
        "--candidate",
        type=str,
        default=str(SCRIPT_DIR / "benchmark_results_ray_grid.json"),
        help="New JSON to compare",
    )
    report.add_argument("--baseline-label", type=str, default="p01 MIMD")
    report.add_argument("--candidate-label", type=str, default="p02 Ray")
    report.add_argument(
        "--demo",
        action="store_true",
        help="Demo script for lecture: local PC vs Grid (ASCII English, terminal-safe)",
    )
    report.add_argument(
        "--demo-file",
        type=str,
        default="",
        help="Also save demo report to this path (UTF-8), e.g. benchmark_demo.txt",
    )
    report.set_defaults(func=cmd_report)

    load = sub.add_parser("load", help="Run headless MC benchmark (from head machine)")
    load.add_argument(
        "--preset",
        choices=["lab", "control", "extinction", "explosion"],
        default="lab",
        help="Simulation size (lab = weak nodes)",
    )
    load.add_argument("--steps", type=int, default=30)
    load.add_argument(
        "--backend",
        choices=["pool", "numpy", "ray"],
        default="ray",
        help="Execution backend (use --compare to run all three)",
    )
    load.add_argument("--compare", action="store_true", help="Benchmark pool, numpy, and ray")
    load.add_argument("--workers", type=int, default=None, help="Chunk count / pool size")
    load.add_argument("--fuel", type=float, default=None)
    load.add_argument("--fast", type=int, default=None)
    load.add_argument("--slow", type=int, default=None)
    load.add_argument(
        "--wait-nodes",
        type=int,
        default=0,
        help="Wait until N nodes are alive (e.g. 3 = head + 2 workers)",
    )
    load.add_argument("--wait-timeout", type=int, default=180)
    load.add_argument(
        "--out",
        type=str,
        default=str(SCRIPT_DIR / "benchmark_results_ray_grid.json"),
    )
    load.set_defaults(func=cmd_load)

    return parser


def main():
    _ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except subprocess.CalledProcessError as exc:
        print(f"Command failed with exit code {exc.returncode}", file=sys.stderr)
        sys.exit(exc.returncode)
    except TimeoutError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
