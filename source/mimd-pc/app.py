#!/usr/bin/env python3
"""
Monte Carlo Reactor Simulation (MIMD PC Implementation)
Course: Cloud and Grid Systems
Includes Interactive Web UI & Headless Benchmark Mode
"""

import argparse
import json
import math
import os
import random
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from multiprocessing import Pool, cpu_count

class ReactorSimulationEngine:
    def __init__(self):
        self.reset_params({
            "fuel_mass": 50,           # Кількість палива (%)
            "n_fast": 350000,          # Швидкі нейтрони
            "n_slow": 150000,          # Повільні нейтрони
            "num_workers": cpu_count()
        })

    def reset_params(self, params):
        self.fuel_mass = float(params.get("fuel_mass", 50))
        self.n_fast = int(params.get("n_fast", 350000))
        self.n_slow = int(params.get("n_slow", 150000))
        self.num_workers = int(params.get("num_workers") or cpu_count())
        
        self.radius = 1000.0  # Фізичний радіус реактора (1000 см = 10 метрів)
        self.tick_count = 0
        self.total_born = self.n_fast + self.n_slow
        self.total_fissions = 0
        self.total_absorbed = 0
        self.total_escaped = 0

        self.neutrons = []
        for _ in range(self.n_fast):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(20.0, 35.0)
            r = random.uniform(0, 250.0)
            self.neutrons.append({
                "x": r * math.cos(angle),
                "y": r * math.sin(angle),
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed,
                "type": "fast",
                "life": 0
            })
        for _ in range(self.n_slow):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(8.0, 14.0)
            r = random.uniform(0, 250.0)
            self.neutrons.append({
                "x": r * math.cos(angle),
                "y": r * math.sin(angle),
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed,
                "type": "slow",
                "life": 0
            })

    def get_state(self):
        active_count = len(self.neutrons)
        if active_count > 1200000:
            status = "EXPLOSION"
        elif active_count < 10000:
            status = "EXTINCTION"
        else:
            status = "STABLE_RUN"

        sample_neutrons = random.sample(self.neutrons, min(750, active_count)) if active_count > 0 else []

        return {
            "tick": self.tick_count,
            "status": status,
            "k_factor": 1.0 if active_count > 0 else 0.0,
            "active_neutrons": active_count,
            "total_fissions": self.total_fissions,
            "total_absorbed": self.total_absorbed,
            "total_escaped": self.total_escaped,
            "fuel_mass": self.fuel_mass,
            "calc_time_ms": 0.0,
            "neutrons": sample_neutrons
        }

    def step(self):
        self.tick_count += 1
        active_count = len(self.neutrons)
        
        if active_count == 0 or active_count > 3500000:
            return self.get_state()

        start_time = time.perf_counter()
        fuel_ratio = self.fuel_mass / 100.0

        chunk_size = max(1, len(self.neutrons) // self.num_workers)
        chunks = [self.neutrons[i:i + chunk_size] for i in range(0, len(self.neutrons), chunk_size)]
        
        task_args = []
        base_seed = random.randint(1, 1_000_000)
        for idx, chunk in enumerate(chunks):
            task_args.append((chunk, fuel_ratio, self.radius, base_seed + idx))

        with Pool(processes=min(self.num_workers, len(chunks))) as pool:
            results = pool.map(update_neutrons_chunk, task_args)

        elapsed = time.perf_counter() - start_time

        next_neutrons = []
        new_fissions = 0
        new_absorbed = 0
        new_escaped = 0
        new_born = 0

        for res in results:
            next_neutrons.extend(res["survived"])
            new_fissions += res["fissions"]
            new_absorbed += res["absorbed"]
            new_escaped += res["escaped"]
            new_born += res["new_born"]

        self.neutrons = next_neutrons
        self.total_fissions += new_fissions
        self.total_absorbed += new_absorbed
        self.total_escaped += new_escaped
        self.total_born += new_born

        current_active = len(self.neutrons)
        prev_active = max(1, active_count)
        
        k_current = (current_active + new_fissions * 2.0) / (prev_active + new_absorbed + new_escaped)

        if current_active == 0:
            status = "EXTINCTION"
            k_current = 0.0
        elif current_active > 900000 and k_current > 1.10:
            status = "EXPLOSION"
        elif current_active < 50000 or (current_active < 150000 and k_current < 0.85):
            status = "EXTINCTION"
        else:
            status = "STABLE_RUN"

        sample_neutrons = random.sample(self.neutrons, min(750, current_active)) if current_active > 0 else []

        return {
            "tick": self.tick_count,
            "status": status,
            "k_factor": round(k_current, 3),
            "active_neutrons": current_active,
            "total_fissions": self.total_fissions,
            "total_absorbed": self.total_absorbed,
            "total_escaped": self.total_escaped,
            "fuel_mass": self.fuel_mass,
            "calc_time_ms": round(elapsed * 1000, 1),
            "neutrons": sample_neutrons
        }

def update_neutrons_chunk(args):
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

        fission_prob = 0.05 * fuel_ratio if n["type"] == "fast" else 0.17 * fuel_ratio
        absorb_prob = 0.11 * (1.1 - fuel_ratio * 0.4)
        scatter_prob = 0.45

        r = random.random()
        if r < fission_prob:
            fissions += 1
            num_spawn = 2 if random.random() < 0.75 else 3
            for _ in range(num_spawn):
                spawn_angle = random.uniform(0, 2 * math.pi)
                spawn_type = "fast" if random.random() < 0.6 else "slow"
                speed = random.uniform(18.0, 30.0) if spawn_type == "fast" else random.uniform(7.0, 13.0)
                survived.append({
                    "x": nx, "y": ny,
                    "vx": math.cos(spawn_angle) * speed,
                    "vy": math.sin(spawn_angle) * speed,
                    "type": spawn_type,
                    "life": 0
                })
                new_born += 1
        elif r < (fission_prob + absorb_prob):
            absorbed += 1
        elif r < (fission_prob + absorb_prob + scatter_prob):
            angle = random.uniform(0, 2 * math.pi)
            speed = math.sqrt(n["vx"]**2 + n["vy"]**2)
            n_type = n["type"]
            if n_type == "fast" and random.random() < 0.25:
                n_type = "slow"
                speed *= 0.5
                
            survived.append({
                "x": nx, "y": ny,
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed,
                "type": n_type,
                "life": n["life"] + 1
            })
        else:
            survived.append({
                "x": nx, "y": ny,
                "vx": n["vx"], "vy": n["vy"],
                "type": n["type"],
                "life": n["life"] + 1
            })

    return {
        "survived": survived,
        "fissions": fissions,
        "absorbed": absorbed,
        "escaped": escaped,
        "new_born": new_born
    }

engine = ReactorSimulationEngine()

# HTML Dashboard
HTML_PAGE = """<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Моделювання Реактора: Monte Carlo MIMD (Mega Scale 1M+)</title>
    <style>
        :root {
            --bg-color: #090d16;
            --panel-bg: #131b2e;
            --text-color: #f1f5f9;
            --accent-color: #38bdf8;
            --border-color: #212e4a;
        }
        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 1300px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: 360px 1fr;
            gap: 20px;
        }
        header {
            grid-column: 1 / -1;
            background: var(--panel-bg);
            padding: 16px 25px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        h1 { margin: 0; font-size: 1.35rem; color: var(--accent-color); }
        .panel {
            background: var(--panel-bg);
            padding: 20px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
        }
        .form-group { margin-bottom: 16px; }
        label { display: block; font-size: 0.88rem; color: #cbd5e1; margin-bottom: 6px; font-weight: 600; }
        .val-disp { float: right; color: var(--accent-color); font-weight: bold; }
        input[type="range"] {
            width: 100%;
            background: #090d16;
            border-radius: 6px;
            accent-color: var(--accent-color);
        }
        .preset-title { font-size: 0.85rem; color: #94a3b8; font-weight: bold; margin-bottom: 8px; text-transform: uppercase; }
        .preset-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 20px; }
        .btn-preset {
            padding: 11px 5px;
            font-size: 0.85rem;
            font-weight: bold;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            cursor: pointer;
            text-align: center;
            transition: all 0.2s;
        }
        .preset-exp { background: #450a0a; color: #fca5a5; border-color: #7f1d1d; }
        .preset-exp:hover { background: #7f1d1d; }
        .preset-ctrl { background: #064e3b; color: #6ee7b7; border-color: #047857; }
        .preset-ctrl:hover { background: #047857; }
        .preset-ext { background: #1e293b; color: #94a3b8; border-color: #475569; }
        .preset-ext:hover { background: #334155; }

        .btn-main {
            width: 100%;
            padding: 14px;
            font-size: 1.05rem;
            font-weight: bold;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            background: #0284c7;
            color: white;
        }
        .btn-main:hover { background: #0369a1; }

        #result-banner {
            font-size: 1.35rem;
            font-weight: 800;
            text-align: center;
            padding: 14px;
            border-radius: 10px;
            margin-bottom: 15px;
            transition: all 0.3s;
        }
        .status-explosion { background: #7f1d1d; color: #fca5a5; border: 2px solid #ef4444; box-shadow: 0 0 25px rgba(239,68,68,0.5); }
        .status-stable { background: #064e3b; color: #6ee7b7; border: 2px solid #10b981; box-shadow: 0 0 25px rgba(16,185,129,0.5); }
        .status-extinction { background: #1e293b; color: #94a3b8; border: 2px solid #64748b; }

        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
            margin-bottom: 15px;
        }
        .metric-card {
            background: #090d16;
            padding: 10px;
            border-radius: 8px;
            text-align: center;
            border: 1px solid var(--border-color);
        }
        .metric-val { font-size: 1.3rem; font-weight: bold; color: var(--accent-color); }
        .metric-lbl { font-size: 0.72rem; color: #94a3b8; }

        #canvas-box {
            display: flex;
            justify-content: center;
            align-items: center;
            background: #040711;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            padding: 10px;
        }
        canvas { background: #020307; border-radius: 8px; }
        .legend { display: flex; justify-content: center; gap: 20px; margin-top: 10px; font-size: 0.85rem; }
        .legend-item { display: flex; align-items: center; gap: 6px; }
        .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>Моделювання ланцюгової реакції реактора (MIMD Monte Carlo)</h1>
                <div style="font-size: 0.85rem; color: #94a3b8;">Мега-масштаб: 1,000,000+ частинок на CPU кластері</div>
            </div>
            <div style="background: #1e293b; padding: 8px 16px; border-radius: 20px; font-weight: bold; font-size: 0.85rem; color: var(--accent-color);">
                MIMD Architecture Engine
            </div>
        </header>

        <div class="panel">
            <div class="preset-title">Готові Демо-Пресет Режими</div>
            <div class="preset-grid">
                <button class="btn-preset preset-exp" onclick="loadPreset('explosion')">💥 Вибух</button>
                <button class="btn-preset preset-ctrl" onclick="loadPreset('control')">🔋 Контроль</button>
                <button class="btn-preset preset-ext" onclick="loadPreset('extinction')">❄️ Затухання</button>
            </div>

            <h3 style="margin-top:10px; color:var(--accent-color); font-size: 1rem;">1. Вхідні параметри</h3>
            
            <div class="form-group">
                <label>Кількість палива в реакторі: <span class="val-disp" id="disp-fuel">50%</span></label>
                <input type="range" id="fuel_mass" min="10" max="100" value="50" oninput="document.getElementById('disp-fuel').innerText = this.value + '%'">
            </div>

            <div class="form-group">
                <label>Швидкі нейтрони (Fast): <span class="val-disp" id="disp-fast">350 000</span></label>
                <input type="range" id="n_fast" min="50000" max="800000" value="350000" step="50000" oninput="document.getElementById('disp-fast').innerText = Number(this.value).toLocaleString()">
            </div>

            <div class="form-group">
                <label>Повільні нейтрони (Slow): <span class="val-disp" id="disp-slow">150 000</span></label>
                <input type="range" id="n_slow" min="0" max="400000" value="150000" step="25000" oninput="document.getElementById('disp-slow').innerText = Number(this.value).toLocaleString()">
            </div>

            <button class="btn-main" id="btn-toggle" onclick="toggleRun()">▶ Запустити неперервно</button>
        </div>

        <div class="panel" style="display: flex; flex-direction: column;">
            
            <div id="result-banner" class="status-stable">
                🔋 ЗАПУСК РЕАКТОРУ (СТАБІЛЬНИЙ РЕЖИМ)
            </div>

            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-val" id="m-active">500,000</div>
                    <div class="metric-lbl">Активні нейтрони</div>
                </div>
                <div class="metric-card">
                    <div class="metric-val" id="m-fissions">0</div>
                    <div class="metric-lbl">Актів ділення ядра</div>
                </div>
                <div class="metric-card">
                    <div class="metric-val" id="m-k">1.00</div>
                    <div class="metric-lbl">Коефіцієнт k</div>
                </div>
                <div class="metric-card">
                    <div class="metric-val" id="m-time">0.0 ms</div>
                    <div class="metric-lbl">Час розрахунку CPU</div>
                </div>
            </div>

            <div id="canvas-box">
                <canvas id="sim-canvas" width="560" height="560"></canvas>
            </div>

            <div class="legend">
                <div class="legend-item"><span class="dot" style="background:#38bdf8;"></span> Швидкі нейтрони</div>
                <div class="legend-item"><span class="dot" style="background:#f59e0b;"></span> Повільні (Теплові) нейтрони</div>
                <div class="legend-item"><span class="dot" style="background:#ef4444; border: 1px solid #fff;"></span> Фізична межа (R = 1000 см)</div>
            </div>
        </div>
    </div>

    <script>
        const canvas = document.getElementById('sim-canvas');
        const ctx = canvas.getContext('2d');
        const W = canvas.width;
        const H = canvas.height;
        const center = W / 2;
        const R_px = W * 0.42;

        let isRunning = false;
        let timerId = null;

        function drawReactorCore() {
            ctx.clearRect(0, 0, W, H);
            
            ctx.beginPath();
            ctx.arc(center, center, R_px, 0, 2 * Math.PI);
            ctx.fillStyle = 'rgba(15, 23, 42, 0.6)';
            ctx.fill();
            ctx.strokeStyle = '#38bdf8';
            ctx.lineWidth = 3;
            ctx.stroke();

            ctx.fillStyle = '#64748b';
            ctx.font = '12px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('Активна зона реактора (R = 1000 см)', center, center + R_px + 18);
        }

        drawReactorCore();

        async function stepSimulation() {
            try {
                const res = await fetch('/api/step', { method: 'POST' });
                const data = await res.json();

                const banner = document.getElementById('result-banner');
                if (data.status === 'EXPLOSION') {
                    banner.className = 'status-explosion';
                    banner.innerText = '💥 ВИБУХ (НАДКРИТИЧНИЙ СТАН)';
                } else if (data.status === 'EXTINCTION') {
                    banner.className = 'status-extinction';
                    banner.innerText = '❄️ ЗАТУХАННЯ (ПІДКРИТИЧНИЙ СТАН)';
                } else {
                    banner.className = 'status-stable';
                    banner.innerText = '🔋 ЗАПУСК РЕАКТОРУ (СТАБІЛЬНИЙ РЕЖИМ)';
                }

                document.getElementById('m-active').innerText = Number(data.active_neutrons).toLocaleString();
                document.getElementById('m-fissions').innerText = Number(data.total_fissions).toLocaleString();
                document.getElementById('m-k').innerText = data.k_factor;
                document.getElementById('m-time').innerText = data.calc_time_ms + ' ms';

                drawReactorCore();
                const scale = R_px / 1000.0;

                ctx.save();
                ctx.beginPath();
                ctx.arc(center, center, R_px - 3, 0, 2 * Math.PI);
                ctx.clip();

                data.neutrons.forEach(n => {
                    const px = center + n.x * scale;
                    const py = center + n.y * scale;

                    ctx.beginPath();
                    ctx.arc(px, py, n.type === 'fast' ? 2.5 : 4.0, 0, 2 * Math.PI);
                    ctx.fillStyle = n.type === 'fast' ? '#38bdf8' : '#f59e0b';
                    ctx.fill();
                    
                    if (n.type === 'slow') {
                        ctx.strokeStyle = '#fff';
                        ctx.lineWidth = 1;
                        ctx.stroke();
                    }
                });

                ctx.restore();

            } catch (err) {
                console.error("Step error:", err);
            }
        }

        function toggleRun() {
            const btn = document.getElementById('btn-toggle');
            if (isRunning) {
                isRunning = false;
                clearInterval(timerId);
                btn.innerText = '▶ Запустити неперервно';
                btn.style.background = '#0284c7';
            } else {
                isRunning = true;
                btn.innerText = '⏸ Пауза';
                btn.style.background = '#ea580c';
                timerId = setInterval(stepSimulation, 250);
            }
        }

        async function applyParams(params) {
            await fetch('/api/reset', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(params)
            });

            drawReactorCore();
            stepSimulation();
        }

        function loadPreset(name) {
            if (name === 'explosion') {
                document.getElementById('fuel_mass').value = 90;
                document.getElementById('n_fast').value = 600000;
                document.getElementById('n_slow').value = 300000;
            } else if (name === 'control') {
                document.getElementById('fuel_mass').value = 50;
                document.getElementById('n_fast').value = 350000;
                document.getElementById('n_slow').value = 150000;
            } else if (name === 'extinction') {
                document.getElementById('fuel_mass').value = 25;
                document.getElementById('n_fast').value = 150000;
                document.getElementById('n_slow').value = 30000;
            }

            document.getElementById('disp-fuel').innerText = document.getElementById('fuel_mass').value + '%';
            document.getElementById('disp-fast').innerText = Number(document.getElementById('n_fast').value).toLocaleString();
            document.getElementById('disp-slow').innerText = Number(document.getElementById('n_slow').value).toLocaleString();

            applyParams({
                fuel_mass: document.getElementById('fuel_mass').value,
                n_fast: document.getElementById('n_fast').value,
                n_slow: document.getElementById('n_slow').value
            });
        }
    </script>
</body>
</html>
"""

class ReactorHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/reset":
            len_b = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(len_b)
            params = json.loads(body.decode("utf-8")) if body else {}
            engine.reset_params(params)
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
            
        elif self.path == "/api/step":
            state = engine.step()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(state).encode("utf-8"))
        else:
            self.send_error(404)

def run_headless_benchmark(params, max_steps=30, output_file="source/mimd-pc/benchmark_results_mimd_pc.json"):
    """
    Executes Monte Carlo Reactor simulation in Headless CLI Benchmark Mode.
    Measures exact wall-clock time, step latency, and particle throughput.
    Saves JSON results for future comparative analysis across architectures.
    """
    print("============================================================")
    print(" MIMD Monte Carlo Reactor Headless Benchmark")
    print("============================================================")
    print(f"Architecture:         MIMD (Multi-core PC)")
    print(f"CPU Workers (Cores):   {params.get('num_workers')}")
    print(f"Fuel Mass:             {params.get('fuel_mass')}%")
    print(f"Initial Fast Neutrons: {params.get('n_fast'):,}")
    print(f"Initial Slow Neutrons: {params.get('n_slow'):,}")
    print(f"Max Benchmark Steps:   {max_steps}")
    print("------------------------------------------------------------")
    print("Running simulation steps...")
    
    engine.reset_params(params)
    
    start_wall = time.perf_counter()
    step_times = []
    
    for s in range(1, max_steps + 1):
        t_start = time.perf_counter()
        state = engine.step()
        t_end = time.perf_counter()
        step_elapsed = t_end - t_start
        step_times.append(step_elapsed)
        
        print(f"  Step {s:02d}/{max_steps}: Active = {state['active_neutrons']:,} | k = {state['k_factor']} | Status = {state['status']} ({step_elapsed*1000:.1f} ms)")
        
        if state['status'] in ("EXPLOSION", "EXTINCTION"):
            print(f"--> Simulation reached terminal condition on step {s}: {state['status']}")
            break
            
    total_wall = time.perf_counter() - start_wall
    avg_step_ms = (sum(step_times) / len(step_times)) * 1000 if step_times else 0.0
    throughput = (engine.total_born + engine.total_fissions) / max(total_wall, 0.0001)
    
    benchmark_data = {
        "architecture": "MIMD_PC",
        "cpu_workers": params.get('num_workers'),
        "fuel_mass": params.get('fuel_mass'),
        "initial_fast": params.get('n_fast'),
        "initial_slow": params.get('n_slow'),
        "total_steps_executed": len(step_times),
        "total_fissions": engine.total_fissions,
        "total_absorbed": engine.total_absorbed,
        "total_escaped": engine.total_escaped,
        "final_active_neutrons": len(engine.neutrons),
        "final_status": state['status'],
        "metrics": {
            "total_execution_time_sec": round(total_wall, 4),
            "avg_step_time_ms": round(avg_step_ms, 2),
            "throughput_particles_per_sec": round(throughput, 1)
        }
    }
    
    # Write JSON results file
    out_dir = os.path.dirname(output_file)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)
        
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, indent=2, ensure_ascii=False)
        
    print("------------------------------------------------------------")
    print(f"Total Execution Time:   {total_wall:.4f} seconds")
    print(f"Average Step Time:      {avg_step_ms:.2f} ms/step")
    print(f"Particle Throughput:    {throughput:,.1f} particles/second")
    print(f"Results saved to:       {output_file}")
    print("============================================================")
    return benchmark_data

def main():
    parser = argparse.ArgumentParser(description="Monte Carlo Reactor MIMD Simulation & Benchmark")
    parser.add_argument("--headless", action="store_true", help="Run in Headless CLI Benchmark Mode without Web UI")
    parser.add_argument("--fuel", type=float, default=50.0, help="Fuel Mass Percentage [10..100]")
    parser.add_argument("--fast", type=int, default=350000, help="Initial Fast Neutrons Count")
    parser.add_argument("--slow", type=int, default=150000, help="Initial Slow Neutrons Count")
    parser.add_argument("--steps", type=int, default=30, help="Max Simulation Steps for Headless Mode")
    parser.add_argument("--workers", type=int, default=cpu_count(), help="Number of CPU Worker Processes")
    parser.add_argument("--port", type=int, default=8080, help="HTTP Web Server Port")
    parser.add_argument("--out", type=str, default="source/mimd-pc/benchmark_results_mimd_pc.json", help="JSON Output File Path for Headless Mode")
    
    args = parser.parse_args()

    if args.headless:
        params = {
            "fuel_mass": args.fuel,
            "n_fast": args.fast,
            "n_slow": args.slow,
            "num_workers": args.workers
        }
        run_headless_benchmark(params, max_steps=args.steps, output_file=args.out)
    else:
        server_address = ("", args.port)
        httpd = HTTPServer(server_address, ReactorHandler)
        print(f"=== Monte Carlo Reactor Simulation (MIMD PC 1M+ Scale) ===")
        print(f"Server running at http://localhost:{args.port}/")
        print(f"CPU Cores Available: {cpu_count()}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")

if __name__ == "__main__":
    main()
