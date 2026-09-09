#!/usr/bin/env python3
"""
Monte Carlo Reactor — Ray Grid stage (batch backends: pool / numpy / ray).
Course: Cloud and Grid Systems
"""

from __future__ import annotations

import json
import sys
import math
import os
import random
import time
from multiprocessing import Pool, cpu_count

import numpy as np

try:
    import ray
except ImportError:  # pragma: no cover - optional until ray install
    ray = None

NEUTRON_DTYPE = np.dtype(
    [
        ("x", "f8"),
        ("y", "f8"),
        ("vx", "f8"),
        ("vy", "f8"),
        ("type", "i1"),  # 0 = fast, 1 = slow
        ("life", "i4"),
    ]
)

PRESETS = {
    "lab": {
        "fuel_mass": 50,
        "n_fast": 50_000,
        "n_slow": 20_000,
        "description": "Легкий пресет для слабких вузлів (Athlon, старий сервер)",
    },
    "control": {
        "fuel_mass": 50,
        "n_fast": 350_000,
        "n_slow": 150_000,
        "description": "Критичний режим (~500k нейтронів)",
    },
    "extinction": {
        "fuel_mass": 25,
        "n_fast": 150_000,
        "n_slow": 30_000,
        "description": "Затухання реакції",
    },
    "explosion": {
        "fuel_mass": 90,
        "n_fast": 600_000,
        "n_slow": 300_000,
        "description": "Мега-масштаб 1M+ (лише для потужного head)",
    },
}

SHARED_POOL = None


def get_shared_pool(num_workers=None):
    global SHARED_POOL
    if SHARED_POOL is None:
        workers = num_workers or cpu_count()
        SHARED_POOL = Pool(processes=workers)
    return SHARED_POOL


def shutdown_shared_pool(terminate=False):
    global SHARED_POOL
    if SHARED_POOL is not None:
        if terminate:
            SHARED_POOL.terminate()
        else:
            SHARED_POOL.close()
        SHARED_POOL.join()
        SHARED_POOL = None


def empty_neutron_array():
    return np.zeros(0, dtype=NEUTRON_DTYPE)


def _spawn_neutron_dict(nx, ny, rng):
    spawn_angle = rng.uniform(0, 2 * math.pi)
    spawn_type = "fast" if rng.random() < 0.6 else "slow"
    if spawn_type == "fast":
        speed = rng.uniform(18.0, 30.0)
        type_code = 0
    else:
        speed = rng.uniform(7.0, 13.0)
        type_code = 1
    return {
        "x": nx,
        "y": ny,
        "vx": math.cos(spawn_angle) * speed,
        "vy": math.sin(spawn_angle) * speed,
        "type": type_code,
        "life": 0,
    }


def _spawn_neutron_record(nx, ny, rng):
    rec = _spawn_neutron_dict(nx, ny, rng)
    return (
        rec["x"],
        rec["y"],
        rec["vx"],
        rec["vy"],
        rec["type"],
        rec["life"],
    )


def generate_initial_neutrons(n_fast, n_slow, rng=None):
    rng = rng or np.random.default_rng()
    total = n_fast + n_slow
    neutrons = empty_neutron_array()
    if total == 0:
        return neutrons

    records = []
    for _ in range(n_fast):
        angle = rng.uniform(0, 2 * math.pi)
        speed = rng.uniform(20.0, 35.0)
        r = rng.uniform(0, 250.0)
        records.append(
            (
                r * math.cos(angle),
                r * math.sin(angle),
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                0,
                0,
            )
        )
    for _ in range(n_slow):
        angle = rng.uniform(0, 2 * math.pi)
        speed = rng.uniform(8.0, 14.0)
        r = rng.uniform(0, 250.0)
        records.append(
            (
                r * math.cos(angle),
                r * math.sin(angle),
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                1,
                0,
            )
        )

    neutrons = np.array(records, dtype=NEUTRON_DTYPE)
    rng.shuffle(neutrons)
    return neutrons


def update_neutrons_scalar_chunk(args):
    """p01-compatible worker: list[dict] in/out."""
    neutrons, fuel_ratio, radius, seed = args
    random.seed(seed)

    survived = []
    fissions = 0
    absorbed = 0
    escaped = 0
    new_born = 0
    max_radius = radius - 15.0

    for n in neutrons:
        nx = n["x"] + n["vx"]
        ny = n["y"] + n["vy"]
        dist = math.sqrt(nx * nx + ny * ny)

        if dist >= max_radius:
            escaped += 1
            continue

        n_type = n["type"]
        is_fast = n_type == 0 or n_type == "fast"
        fission_prob = 0.05 * fuel_ratio if is_fast else 0.17 * fuel_ratio
        absorb_prob = 0.11 * (1.1 - fuel_ratio * 0.4)
        scatter_prob = 0.45

        r = random.random()
        if r < fission_prob:
            fissions += 1
            num_spawn = 2 if random.random() < 0.75 else 3
            for _ in range(num_spawn):
                survived.append(_spawn_neutron_dict(nx, ny, random))
                new_born += 1
        elif r < (fission_prob + absorb_prob):
            absorbed += 1
        elif r < (fission_prob + absorb_prob + scatter_prob):
            angle = random.uniform(0, 2 * math.pi)
            speed = math.sqrt(n["vx"] ** 2 + n["vy"] ** 2)
            out_type = 0 if is_fast else 1
            if is_fast and random.random() < 0.25:
                out_type = 1
                speed *= 0.5
            survived.append(
                {
                    "x": nx,
                    "y": ny,
                    "vx": math.cos(angle) * speed,
                    "vy": math.sin(angle) * speed,
                    "type": out_type,
                    "life": n.get("life", 0) + 1,
                }
            )
        else:
            survived.append(
                {
                    "x": nx,
                    "y": ny,
                    "vx": n["vx"],
                    "vy": n["vy"],
                    "type": 0 if is_fast else 1,
                    "life": n.get("life", 0) + 1,
                }
            )

    return {
        "survived": survived,
        "fissions": fissions,
        "absorbed": absorbed,
        "escaped": escaped,
        "new_born": new_born,
    }


def _numpy_chunk_worker(args):
    return update_neutrons_numpy_chunk(*args)


def update_neutrons_numpy_chunk(neutrons, fuel_ratio, radius, seed):
    """NumPy structured array worker (used by numpy and ray backends)."""
    rng = np.random.default_rng(seed)
    if len(neutrons) == 0:
        return {
            "survived": empty_neutron_array(),
            "fissions": 0,
            "absorbed": 0,
            "escaped": 0,
            "new_born": 0,
        }

    max_radius = radius - 15.0
    survived_records = []
    fissions = 0
    absorbed = 0
    escaped = 0
    new_born = 0

    nx = neutrons["x"] + neutrons["vx"]
    ny = neutrons["y"] + neutrons["vy"]
    dist = np.hypot(nx, ny)

    escaped = int(np.count_nonzero(dist >= max_radius))
    survivor_idx = np.where(dist < max_radius)[0]

    for i in survivor_idx:
        px, py = float(nx[i]), float(ny[i])
        is_fast = int(neutrons["type"][i]) == 0
        fission_prob = 0.05 * fuel_ratio if is_fast else 0.17 * fuel_ratio
        absorb_prob = 0.11 * (1.1 - fuel_ratio * 0.4)
        scatter_prob = 0.45

        r = rng.random()
        if r < fission_prob:
            fissions += 1
            num_spawn = 2 if rng.random() < 0.75 else 3
            for _ in range(num_spawn):
                survived_records.append(_spawn_neutron_record(px, py, rng))
                new_born += 1
        elif r < (fission_prob + absorb_prob):
            absorbed += 1
        elif r < (fission_prob + absorb_prob + scatter_prob):
            angle = rng.uniform(0, 2 * math.pi)
            speed = math.sqrt(neutrons["vx"][i] ** 2 + neutrons["vy"][i] ** 2)
            out_type = 0 if is_fast else 1
            if is_fast and rng.random() < 0.25:
                out_type = 1
                speed *= 0.5
            survived_records.append(
                (
                    px,
                    py,
                    math.cos(angle) * speed,
                    math.sin(angle) * speed,
                    out_type,
                    int(neutrons["life"][i]) + 1,
                )
            )
        else:
            survived_records.append(
                (
                    px,
                    py,
                    float(neutrons["vx"][i]),
                    float(neutrons["vy"][i]),
                    int(neutrons["type"][i]),
                    int(neutrons["life"][i]) + 1,
                )
            )

    if survived_records:
        survived = np.array(survived_records, dtype=NEUTRON_DTYPE)
    else:
        survived = empty_neutron_array()

    return {
        "survived": survived,
        "fissions": fissions,
        "absorbed": absorbed,
        "escaped": escaped,
        "new_born": new_born,
    }


if ray is not None:

    @ray.remote
    def update_neutrons_remote(neutrons, fuel_ratio, radius, seed):
        return update_neutrons_numpy_chunk(neutrons, fuel_ratio, radius, seed)


def _neutrons_to_scalar_chunks(neutrons_np, num_workers):
    dicts = [
        {
            "x": float(n["x"]),
            "y": float(n["y"]),
            "vx": float(n["vx"]),
            "vy": float(n["vy"]),
            "type": int(n["type"]),
            "life": int(n["life"]),
        }
        for n in neutrons_np
    ]
    if not dicts:
        return []
    chunk_size = max(1, len(dicts) // num_workers)
    return [dicts[i : i + chunk_size] for i in range(0, len(dicts), chunk_size)]


def _split_numpy_chunks(neutrons_np, num_workers):
    if len(neutrons_np) == 0:
        return []
    chunk_count = min(num_workers, len(neutrons_np))
    return [c for c in np.array_split(neutrons_np, chunk_count) if len(c) > 0]


def get_cluster_summary():
    if ray is None or not ray.is_initialized():
        return {"connected": False, "nodes": 0, "cpus": 0, "node_details": []}

    nodes = [n for n in ray.nodes() if n.get("Alive")]
    cpus = int(ray.cluster_resources().get("CPU", 0))
    details = []
    for node in nodes:
        res = node.get("Resources", {})
        details.append(
            {
                "node_id": node.get("NodeID", "")[:8],
                "ip": node.get("NodeManagerAddress", "?"),
                "cpus": int(res.get("CPU", 0)),
            }
        )
    return {
        "connected": True,
        "nodes": len(nodes),
        "cpus": cpus,
        "node_details": details,
    }


class ReactorSimulationEngine:
    def __init__(self, backend="ray"):
        if backend not in ("pool", "numpy", "ray"):
            raise ValueError(f"Unknown backend: {backend}")
        self.backend = backend
        self.radius = 1000.0
        self.reset_params(
            {
                "fuel_mass": 50,
                "n_fast": 50_000,
                "n_slow": 20_000,
                "num_workers": cpu_count(),
            }
        )

    def reset_params(self, params):
        self.fuel_mass = float(params.get("fuel_mass", 50))
        self.n_fast = int(params.get("n_fast", 50_000))
        self.n_slow = int(params.get("n_slow", 20_000))
        self.num_workers = int(params.get("num_workers") or cpu_count())

        self.tick_count = 0
        self.initial_total = self.n_fast + self.n_slow
        self.total_born = self.initial_total
        self.total_fissions = 0
        self.total_absorbed = 0
        self.total_escaped = 0

        seed = int(params.get("seed", random.randint(1, 1_000_000)))
        self.neutrons = generate_initial_neutrons(self.n_fast, self.n_slow, np.random.default_rng(seed))

    def step(self):
        self.tick_count += 1
        active_count = len(self.neutrons)

        if active_count == 0 or active_count > 3_500_000:
            return self._build_state(0.0, self._status_for_count(active_count, 0.0))

        start_time = time.perf_counter()
        fuel_ratio = self.fuel_mass / 100.0
        base_seed = random.randint(1, 1_000_000)

        if self.backend == "pool":
            results = self._step_pool(fuel_ratio, base_seed)
        elif self.backend == "numpy":
            results = self._step_numpy(fuel_ratio, base_seed)
        else:
            results = self._step_ray(fuel_ratio, base_seed)

        elapsed = time.perf_counter() - start_time

        next_parts = []
        new_fissions = 0
        new_absorbed = 0
        new_escaped = 0
        new_born = 0

        for res in results:
            next_parts.append(res["survived"])
            new_fissions += res["fissions"]
            new_absorbed += res["absorbed"]
            new_escaped += res["escaped"]
            new_born += res["new_born"]

        if next_parts:
            if self.backend == "pool":
                flat = []
                for part in next_parts:
                    flat.extend(part)
                if flat:
                    self.neutrons = np.array(
                        [
                            (
                                d["x"],
                                d["y"],
                                d["vx"],
                                d["vy"],
                                int(d["type"]) if isinstance(d["type"], int) else (0 if d["type"] == "fast" else 1),
                                int(d.get("life", 0)),
                            )
                            for d in flat
                        ],
                        dtype=NEUTRON_DTYPE,
                    )
                else:
                    self.neutrons = empty_neutron_array()
            else:
                self.neutrons = np.concatenate(next_parts) if len(next_parts) > 1 else next_parts[0]
        else:
            self.neutrons = empty_neutron_array()

        self.total_fissions += new_fissions
        self.total_absorbed += new_absorbed
        self.total_escaped += new_escaped
        self.total_born += new_born

        current_active = len(self.neutrons)
        prev_active = max(1, active_count)
        k_current = (current_active + new_fissions * 2.0) / (prev_active + new_absorbed + new_escaped)
        status = self._status_for_count(current_active, k_current)

        return self._build_state(elapsed * 1000, status, k_current)

    def _step_pool(self, fuel_ratio, base_seed):
        scalar_chunks = _neutrons_to_scalar_chunks(self.neutrons, self.num_workers)
        if not scalar_chunks:
            return []
        task_args = [
            (chunk, fuel_ratio, self.radius, base_seed + idx) for idx, chunk in enumerate(scalar_chunks)
        ]
        pool = get_shared_pool(self.num_workers)
        return pool.map(update_neutrons_scalar_chunk, task_args)

    def _step_numpy(self, fuel_ratio, base_seed):
        chunks = _split_numpy_chunks(self.neutrons, self.num_workers)
        if not chunks:
            return []
        task_args = [
            (chunk, fuel_ratio, self.radius, base_seed + idx) for idx, chunk in enumerate(chunks)
        ]
        pool = get_shared_pool(self.num_workers)
        return pool.map(_numpy_chunk_worker, task_args)

    def _step_ray(self, fuel_ratio, base_seed):
        if ray is None:
            raise RuntimeError("Ray is not installed. Run: pip install 'ray[default]'")
        if not ray.is_initialized():
            ray.init(address="auto", ignore_reinit_error=True)

        chunks = _split_numpy_chunks(self.neutrons, self.num_workers)
        if not chunks:
            return []

        futures = [
            update_neutrons_remote.remote(chunk, fuel_ratio, self.radius, base_seed + idx)
            for idx, chunk in enumerate(chunks)
        ]
        return ray.get(futures)

    def _status_for_count(self, current_active, k_current):
        """Пороги масштабуються від початкової кількості (як у p01 для ~500k)."""
        initial = max(1, self.initial_total)
        extinction_low = max(5_000, int(initial * 0.10))
        extinction_mid = int(initial * 0.30)
        explosion_high = int(initial * 1.8)

        if current_active == 0:
            return "EXTINCTION"
        if current_active > explosion_high and k_current > 1.10:
            return "EXPLOSION"
        if current_active < extinction_low or (current_active < extinction_mid and k_current < 0.85):
            return "EXTINCTION"
        return "STABLE_RUN"

    def _build_state(self, calc_time_ms, status, k_current=0.0):
        current_active = len(self.neutrons)
        return {
            "tick": self.tick_count,
            "status": status,
            "k_factor": round(k_current, 3),
            "active_neutrons": current_active,
            "total_fissions": self.total_fissions,
            "total_absorbed": self.total_absorbed,
            "total_escaped": self.total_escaped,
            "backend": self.backend,
            "calc_time_ms": round(calc_time_ms, 1),
        }


def _run_single_benchmark(backend, params, max_steps, init_ray=False):
    if backend == "ray":
        if ray is None:
            raise RuntimeError("Ray is not installed")
        if not ray.is_initialized():
            ray.init(address="auto", ignore_reinit_error=True)
    elif init_ray and ray is not None and ray.is_initialized():
        pass

    engine = ReactorSimulationEngine(backend=backend)
    engine.reset_params(params)

    cluster = get_cluster_summary() if backend == "ray" else None
    start_wall = time.perf_counter()
    step_times = []
    state = engine._build_state(0.0, "STABLE_RUN", 1.0)

    for step_idx in range(1, max_steps + 1):
        t_start = time.perf_counter()
        state = engine.step()
        step_times.append(time.perf_counter() - t_start)
        print(
            f"  [{backend:5}] Step {step_idx:02d}/{max_steps}: "
            f"Active = {state['active_neutrons']:,} | k = {state['k_factor']} | "
            f"Status = {state['status']} ({state['calc_time_ms']:.1f} ms)"
        )
        if state["status"] in ("EXPLOSION", "EXTINCTION"):
            print(f"  --> Terminal condition on step {step_idx}: {state['status']}")
            break

    total_wall = time.perf_counter() - start_wall
    avg_step_ms = (sum(step_times) / len(step_times)) * 1000 if step_times else 0.0
    throughput = (engine.total_born + engine.total_fissions) / max(total_wall, 1e-4)

    return {
        "architecture": f"RAY_GRID_{backend.upper()}",
        "backend": backend,
        "cpu_workers": params.get("num_workers"),
        "fuel_mass": params.get("fuel_mass"),
        "initial_fast": params.get("n_fast"),
        "initial_slow": params.get("n_slow"),
        "preset": params.get("preset"),
        "total_steps_executed": len(step_times),
        "total_fissions": engine.total_fissions,
        "total_absorbed": engine.total_absorbed,
        "total_escaped": engine.total_escaped,
        "final_active_neutrons": len(engine.neutrons),
        "final_status": state["status"],
        "cluster": cluster,
        "metrics": {
            "total_execution_time_sec": round(total_wall, 4),
            "avg_step_time_ms": round(avg_step_ms, 2),
            "throughput_particles_per_sec": round(throughput, 1),
        },
    }


def _ensure_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def run_headless_benchmark(
    params,
    max_steps=30,
    backend="ray",
    output_file="source/ray-grid/benchmark_results_ray_grid.json",
    compare=False,
):
    _ensure_utf8_stdio()
    print("============================================================")
    print(" Ray Grid Monte Carlo Reactor Headless Benchmark")
    print("============================================================")

    if compare:
        backends = ("pool", "numpy", "ray")
    else:
        backends = (backend,)

    if "ray" in backends and ray is None:
        raise RuntimeError("Ray backend requested but ray is not installed")

    if "ray" in backends:
        if not ray.is_initialized():
            ray.init(address="auto", ignore_reinit_error=True)
        cluster = get_cluster_summary()
        print(f"Ray cluster: {cluster['nodes']} node(s), {cluster['cpus']} CPU(s)")
        for node in cluster["node_details"]:
            print(f"  - {node['ip']}: {node['cpus']} CPU (id {node['node_id']}...)")
        print("------------------------------------------------------------")

    explicit_workers = params.get("num_workers")
    results = []
    try:
        for item in backends:
            bench_params = dict(params)
            bench_params["num_workers"] = resolve_num_workers(item, explicit_workers)
            print(f"Running backend: {item} (workers={bench_params['num_workers']})")
            print("------------------------------------------------------------")
            results.append(_run_single_benchmark(item, bench_params, max_steps))
            print("------------------------------------------------------------")
    finally:
        shutdown_shared_pool()

    payload = {
        "benchmark_suite": "ray_grid_mc_reactor",
        "compare_mode": compare,
        "runs": results if compare else results[0],
    }

    out_dir = os.path.dirname(output_file)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"Results saved to: {output_file}")
    print("============================================================")
    return payload


def resolve_num_workers(backend, explicit=None):
    """pool/numpy — локальні ядра; ray — сумарні CPU кластера (якщо підключений)."""
    if explicit is not None:
        return explicit
    if backend == "ray" and ray is not None:
        if not ray.is_initialized():
            try:
                ray.init(address="auto", ignore_reinit_error=True)
            except Exception:
                return cpu_count()
        return max(1, int(ray.cluster_resources().get("CPU", cpu_count())))
    return cpu_count()


def build_params_from_preset(preset_name, num_workers=None):
    if preset_name not in PRESETS:
        raise ValueError(f"Unknown preset: {preset_name}. Choose from: {', '.join(PRESETS)}")
    preset = PRESETS[preset_name]
    return {
        "preset": preset_name,
        "fuel_mass": preset["fuel_mass"],
        "n_fast": preset["n_fast"],
        "n_slow": preset["n_slow"],
        "num_workers": num_workers,
    }
