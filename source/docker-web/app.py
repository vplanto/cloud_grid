#!/usr/bin/env python3
"""
Containerized Monte Carlo Reactor Simulation Service (Stage 3: Docker & Web)
Course: Cloud and Grid Systems

Features:
- REST API: /api/health, /api/metrics, /api/reset, /api/step, /api/batch
- Interactive WebGL/Canvas Dashboard with real-time telemetry
- Multi-Tenancy session isolation (SessionManager)
- Graceful shutdown on SIGTERM/SIGINT (PID 1 in Docker)
- Configurable via environment variables (PORT, SIM_WORKERS, SIM_FUEL)
"""

import argparse
import json
import math
import os
import random
import signal
import sys
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from multiprocessing import Pool, cpu_count

# --- Configuration from Environment Variables ---
DEFAULT_PORT = int(os.environ.get("PORT", os.environ.get("SIM_PORT", 8080)))
DEFAULT_WORKERS = int(os.environ.get("SIM_WORKERS", cpu_count()))
DEFAULT_FUEL = float(os.environ.get("SIM_FUEL", 50.0))

SHARED_POOL = None

def get_shared_pool(num_workers=None):
    """
    Returns a persistent shared multiprocessing.Pool.
    Reuses worker processes to eliminate fork/exec overhead per step.
    """
    global SHARED_POOL
    if SHARED_POOL is None:
        workers = num_workers or DEFAULT_WORKERS
        SHARED_POOL = Pool(processes=workers)
    return SHARED_POOL

def shutdown_shared_pool(terminate=False):
    """
    Safely shuts down the shared process pool.
    """
    global SHARED_POOL
    if SHARED_POOL is not None:
        if terminate:
            SHARED_POOL.terminate()
        else:
            SHARED_POOL.close()
        SHARED_POOL.join()
        SHARED_POOL = None


class ReactorSimulationEngine:
    def __init__(self, num_workers=None):
        self.reset_params({
            "fuel_mass": DEFAULT_FUEL,
            "n_fast": 350000,
            "n_slow": 150000,
            "num_workers": num_workers or DEFAULT_WORKERS
        })

    def reset_params(self, params):
        self.fuel_mass = float(params.get("fuel_mass", DEFAULT_FUEL))
        self.n_fast = int(params.get("n_fast", 350000))
        self.n_slow = int(params.get("n_slow", 150000))
        self.num_workers = int(params.get("num_workers") or DEFAULT_WORKERS)

        self.radius = 1000.0  # 10 метрів умовного радіуса активної зони
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

    def step(self):
        self.tick_count += 1
        t_start = time.perf_counter()

        initial_count = len(self.neutrons)
        if initial_count == 0:
            return {
                "tick": self.tick_count,
                "status": "EXTINCTION",
                "k_factor": 0.0,
                "active_neutrons": 0,
                "total_fissions": self.total_fissions,
                "total_absorbed": self.total_absorbed,
                "total_escaped": self.total_escaped,
                "fuel_mass": self.fuel_mass,
                "calc_time_ms": 0.0,
                "neutrons": []
            }

        pool = get_shared_pool(self.num_workers)
        chunk_size = math.ceil(initial_count / self.num_workers)
        chunks = []
        fuel_ratio = self.fuel_mass / 100.0

        for i in range(0, initial_count, chunk_size):
            sub_list = self.neutrons[i:i + chunk_size]
            chunks.append((sub_list, fuel_ratio, self.radius, random.randint(0, 10000000)))

        results = pool.map(update_neutrons_chunk, chunks)

        survived_all = []
        step_fissions = 0
        step_absorbed = 0
        step_escaped = 0
        step_new_born = 0

        for res in results:
            survived_all.extend(res["survived"])
            step_fissions += res["fissions"]
            step_absorbed += res["absorbed"]
            step_escaped += res["escaped"]
            step_new_born += res["new_born"]

        self.neutrons = survived_all
        self.total_fissions += step_fissions
        self.total_absorbed += step_absorbed
        self.total_escaped += step_escaped
        self.total_born += step_new_born

        loss = step_absorbed + step_escaped
        k_current = float(step_new_born) / float(loss) if loss > 0 else 1.0

        t_end = time.perf_counter()
        elapsed = t_end - t_start

        current_active = len(self.neutrons)
        if current_active > 1200000 or (current_active > 750000 and k_current > 1.35):
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


class SessionManager:
    """
    Multi-tenant session manager. Isolates reactor state per client.
    """
    def __init__(self, ttl_seconds=300):
        self.sessions = {}
        self.last_active = {}
        self.ttl = ttl_seconds
        self._lock = threading.Lock()

    def get_engine(self, session_id: str) -> ReactorSimulationEngine:
        now = time.time()
        with self._lock:
            self._cleanup_expired(now)
            if session_id not in self.sessions:
                self.sessions[session_id] = ReactorSimulationEngine()
            self.last_active[session_id] = now
            return self.sessions[session_id]

    def session_count(self) -> int:
        with self._lock:
            return len(self.sessions)

    def _cleanup_expired(self, now: float):
        expired = [sid for sid, last in self.last_active.items() if now - last > self.ttl]
        for sid in expired:
            self.sessions.pop(sid, None)
            self.last_active.pop(sid, None)


session_manager = SessionManager(ttl_seconds=300)


HTML_PAGE = """<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Monte Carlo Reactor Simulation (Docker Stage 3)</title>
    <style>
        :root {
            --bg-color: #0b0f19;
            --panel-bg: #111827;
            --panel-border: #1f2937;
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --accent: #38bdf8;
            --accent-glow: rgba(56, 189, 248, 0.25);
            --danger: #ef4444;
            --warning: #f59e0b;
            --success: #10b981;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            padding: 18px;
            display: flex;
            flex-direction: column;
            gap: 16px;
            min-height: 100vh;
        }
        header {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 10px;
            padding: 14px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        header h1 { font-size: 1.25rem; font-weight: 700; color: var(--accent); }
        .badge {
            background: #1e293b;
            color: #38bdf8;
            border: 1px solid #334155;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.75rem;
            font-family: monospace;
            font-weight: 600;
        }
        .main-layout {
            display: grid;
            grid-template-columns: 360px 1fr;
            gap: 16px;
            flex: 1;
        }
        @media (max-width: 900px) {
            .main-layout { grid-template-columns: 1fr; }
        }
        .card {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 10px;
            padding: 18px;
            display: flex;
            flex-direction: column;
            gap: 14px;
        }
        .section-title {
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
            font-weight: 700;
            border-bottom: 1px solid var(--panel-border);
            padding-bottom: 6px;
        }
        .form-row { display: flex; flex-direction: column; gap: 6px; }
        .form-row label {
            font-size: 0.82rem;
            color: var(--text-secondary);
            display: flex;
            justify-content: space-between;
        }
        .form-row input[type="range"] {
            accent-color: var(--accent);
            cursor: pointer;
        }
        .btn-group { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        .btn {
            background: #1f2937;
            color: var(--text-primary);
            border: 1px solid #374151;
            padding: 10px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            font-size: 0.85rem;
            transition: all 0.15s ease;
        }
        .btn:hover { background: #374151; border-color: #4b5563; }
        .btn-primary { background: #0284c7; border-color: #0369a1; color: #fff; }
        .btn-primary:hover { background: #0369a1; }
        .btn-danger { background: #991b1b; border-color: #7f1d1d; color: #fff; }
        .btn-danger:hover { background: #7f1d1d; }

        .metrics-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
        .metric-box {
            background: #0f172a;
            border: 1px solid #1e293b;
            padding: 10px 12px;
            border-radius: 6px;
        }
        .metric-label { font-size: 0.72rem; color: var(--text-secondary); text-transform: uppercase; }
        .metric-value { font-size: 1.15rem; font-weight: 700; color: var(--text-primary); margin-top: 4px; font-family: monospace; }

        .canvas-container {
            position: relative;
            background: #050811;
            border: 1px solid var(--panel-border);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            min-height: 520px;
        }
        canvas {
            display: block;
            width: 100%;
            height: 100%;
            max-width: 650px;
            max-height: 650px;
        }
        .hud-overlay {
            position: absolute;
            top: 14px;
            left: 14px;
            background: rgba(17, 24, 39, 0.85);
            backdrop-filter: blur(4px);
            padding: 8px 12px;
            border-radius: 6px;
            border: 1px solid #374151;
            font-family: monospace;
            font-size: 0.78rem;
            color: #94a3b8;
            pointer-events: none;
        }
        .status-pill {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: 700;
        }
        .status-STABLE_RUN { background: rgba(16, 185, 129, 0.2); color: #34d399; }
        .status-EXPLOSION { background: rgba(239, 68, 68, 0.2); color: #f87171; }
        .status-EXTINCTION { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }
    </style>
</head>
<body>
    <header>
        <div>
            <h1>⚛️ Monte Carlo Reactor Simulation (Stage 3)</h1>
            <p style="font-size: 0.78rem; color: var(--text-secondary); margin-top: 2px;">
                Containerized Microservice & WebGL/Canvas Telemetry Dashboard
            </p>
        </div>
        <div style="display: flex; gap: 8px; align-items: center;">
            <span class="badge" id="sessionBadge">Session: init...</span>
            <span class="badge" style="color: #10b981; border-color: #065f46;">Docker Container</span>
        </div>
    </header>

    <div class="main-layout">
        <aside class="card">
            <div class="section-title">Параметри симуляції</div>

            <div class="form-row">
                <label>Маса палива (Fuel): <span id="fuelVal" style="color: var(--accent); font-weight: bold;">50%</span></label>
                <input type="range" id="fuelMass" min="10" max="100" value="50" step="1">
            </div>

            <div class="form-row">
                <label>Швидкі нейтрони: <span id="fastVal" style="color: var(--accent); font-weight: bold;">350,000</span></label>
                <input type="range" id="nFast" min="50000" max="800000" value="350000" step="25000">
            </div>

            <div class="form-row">
                <label>Повільні нейтрони: <span id="slowVal" style="color: var(--accent); font-weight: bold;">150,000</span></label>
                <input type="range" id="nSlow" min="20000" max="400000" value="150000" step="10000">
            </div>

            <div class="btn-group">
                <button class="btn btn-primary" id="btnToggle">▶ Запуск</button>
                <button class="btn" id="btnStep">⏭ 1 Крок</button>
            </div>
            <div class="btn-group">
                <button class="btn" id="btnReset">🔄 Скинути</button>
                <button class="btn" id="btnBatch">⚡ Batch 10</button>
            </div>

            <div class="section-title" style="margin-top: 8px;">Телеметрія системи</div>
            <div class="metrics-grid">
                <div class="metric-box">
                    <div class="metric-label">Критичність (k)</div>
                    <div class="metric-value" id="kFactor">1.000</div>
                </div>
                <div class="metric-box">
                    <div class="metric-label">Статус</div>
                    <div class="metric-value" style="font-size: 0.95rem;" id="simStatus">
                        <span class="status-pill status-STABLE_RUN">READY</span>
                    </div>
                </div>
                <div class="metric-box">
                    <div class="metric-label">Активні нейтрони</div>
                    <div class="metric-value" id="activeCount">500,000</div>
                </div>
                <div class="metric-box">
                    <div class="metric-label">Час кроку CPU</div>
                    <div class="metric-value" id="calcTime">0.0 ms</div>
                </div>
                <div class="metric-box">
                    <div class="metric-label">Акти ділення</div>
                    <div class="metric-value" id="fissionsCount">0</div>
                </div>
                <div class="metric-box">
                    <div class="metric-label">Вилетіло / Загинуло</div>
                    <div class="metric-value" id="escapedCount">0</div>
                </div>
            </div>
        </aside>

        <main class="canvas-container">
            <canvas id="reactorCanvas" width="600" height="600"></canvas>
            <div class="hud-overlay" id="hudOverlay">
                FPS: <span id="fpsCounter">60</span> | Render sample: <span id="sampleCounter">0</span> | Tick: <span id="tickCounter">0</span>
            </div>
        </main>
    </div>

    <script>
        const canvas = document.getElementById("reactorCanvas");
        const ctx = canvas.getContext("2d");
        let isRunning = false;
        let isCalculating = false;
        let sessionId = localStorage.getItem("sim_session") || ("sess_" + Math.random().toString(36).substring(2, 10));
        localStorage.setItem("sim_session", sessionId);
        document.getElementById("sessionBadge").textContent = "ID: " + sessionId;

        let particles = [];
        let lastFrameTime = performance.now();
        let frameCount = 0;
        let fps = 60;

        // UI Controls
        const fuelSlider = document.getElementById("fuelMass");
        const fastSlider = document.getElementById("nFast");
        const slowSlider = document.getElementById("nSlow");
        fuelSlider.oninput = () => document.getElementById("fuelVal").textContent = fuelSlider.value + "%";
        fastSlider.oninput = () => document.getElementById("fastVal").textContent = Number(fastSlider.value).toLocaleString();
        slowSlider.oninput = () => document.getElementById("slowVal").textContent = Number(slowSlider.value).toLocaleString();

        async function postJson(endpoint, data = {}) {
            const res = await fetch(endpoint, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Simulation-Session": sessionId
                },
                body: JSON.stringify(data)
            });
            return await res.json();
        }

        async function executeStep() {
            if (isCalculating) return;
            isCalculating = true;
            try {
                const data = await postJson("/api/step");
                updateDashboard(data);
            } catch (err) {
                console.error("Step error:", err);
            } finally {
                isCalculating = false;
            }
        }

        function updateDashboard(data) {
            document.getElementById("kFactor").textContent = Number(data.k_factor).toFixed(3);
            document.getElementById("activeCount").textContent = Number(data.active_neutrons).toLocaleString();
            document.getElementById("calcTime").textContent = data.calc_time_ms + " ms";
            document.getElementById("fissionsCount").textContent = Number(data.total_fissions).toLocaleString();
            document.getElementById("escapedCount").textContent = Number(data.total_escaped + data.total_absorbed).toLocaleString();
            document.getElementById("tickCounter").textContent = data.tick;

            const st = document.getElementById("simStatus");
            st.innerHTML = `<span class="status-pill status-${data.status}">${data.status}</span>`;

            if (data.neutrons) {
                particles = data.neutrons;
                document.getElementById("sampleCounter").textContent = particles.length;
            }
        }

        async function resetSimulation() {
            const params = {
                fuel_mass: Number(fuelSlider.value),
                n_fast: Number(fastSlider.value),
                n_slow: Number(slowSlider.value)
            };
            const data = await postJson("/api/reset", params);
            executeStep();
        }

        document.getElementById("btnToggle").onclick = () => {
            isRunning = !isRunning;
            document.getElementById("btnToggle").textContent = isRunning ? "⏸ Пауза" : "▶ Запуск";
            document.getElementById("btnToggle").classList.toggle("btn-danger", isRunning);
        };
        document.getElementById("btnStep").onclick = () => executeStep();
        document.getElementById("btnReset").onclick = () => resetSimulation();
        document.getElementById("btnBatch").onclick = async () => {
            const res = await postJson("/api/batch", { steps: 10 });
            alert(`Batch 10 завершено за ${res.total_time_ms} ms (середній крок: ${res.avg_step_ms} ms)`);
            executeStep();
        };

        // Render loop
        function render(now) {
            frameCount++;
            if (now - lastFrameTime >= 1000) {
                fps = frameCount;
                frameCount = 0;
                lastFrameTime = now;
                document.getElementById("fpsCounter").textContent = fps;
            }

            const w = canvas.width;
            const h = canvas.height;
            const cx = w / 2;
            const cy = h / 2;
            const scale = (w / 2 - 20) / 1000.0;

            ctx.fillStyle = "#050811";
            ctx.fillRect(0, 0, w, h);

            // Reactor Core Boundary
            ctx.strokeStyle = "#1f2937";
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(cx, cy, 1000.0 * scale, 0, Math.PI * 2);
            ctx.stroke();

            // Glow center
            const grad = ctx.createRadialGradient(cx, cy, 10, cx, cy, 1000.0 * scale);
            grad.addColorStop(0, "rgba(56, 189, 248, 0.08)");
            grad.addColorStop(1, "rgba(5, 8, 17, 0)");
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(cx, cy, 1000.0 * scale, 0, Math.PI * 2);
            ctx.fill();

            // Render particles
            for (let i = 0; i < particles.length; i++) {
                const p = particles[i];
                const px = cx + p.x * scale;
                const py = cy + p.y * scale;

                ctx.fillStyle = p.type === "fast" ? "#38bdf8" : "#fbbf24";
                ctx.beginPath();
                ctx.arc(px, py, p.type === "fast" ? 2.0 : 2.5, 0, Math.PI * 2);
                ctx.fill();
            }

            if (isRunning && !isCalculating) {
                executeStep();
            }

            requestAnimationFrame(render);
        }

        requestAnimationFrame(render);
        resetSimulation();
    </script>
</body>
</html>
"""


class SimulationRequestHandler(BaseHTTPRequestHandler):
    def get_session_id(self):
        # 1. Header X-Simulation-Session
        header_sid = self.headers.get("X-Simulation-Session")
        if header_sid:
            return header_sid

        # 2. Cookie sim_session
        cookie = self.headers.get("Cookie", "")
        for item in cookie.split(";"):
            parts = item.strip().split("=")
            if len(parts) == 2 and parts[0] == "sim_session":
                return parts[1]

        return "default_session"

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            sid = self.get_session_id()
            if sid == "default_session":
                sid = "sess_" + uuid.uuid4().hex[:10]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Set-Cookie", f"sim_session={sid}; Path=/; SameSite=Lax")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))

        elif self.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            payload = {
                "status": "healthy",
                "service": "reactor-simulation",
                "stage": "03_docker_web",
                "workers": DEFAULT_WORKERS,
                "timestamp": time.time()
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))

        elif self.path == "/api/metrics":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            payload = {
                "service": "reactor-simulation",
                "active_sessions": session_manager.session_count(),
                "default_workers": DEFAULT_WORKERS,
                "default_fuel": DEFAULT_FUEL,
                "pid": os.getpid()
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))

        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        sid = self.get_session_id()
        engine = session_manager.get_engine(sid)

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            params = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            params = {}

        if self.path == "/api/reset":
            engine.reset_params(params)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", f"sim_session={sid}; Path=/; SameSite=Lax")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "session_id": sid}).encode("utf-8"))

        elif self.path == "/api/step":
            state = engine.step()
            state["session_id"] = sid
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", f"sim_session={sid}; Path=/; SameSite=Lax")
            self.end_headers()
            self.wfile.write(json.dumps(state).encode("utf-8"))

        elif self.path == "/api/batch":
            steps = min(int(params.get("steps", 10)), 100)
            t_start = time.perf_counter()
            states = []
            for _ in range(steps):
                states.append(engine.step())
            t_total = time.perf_counter() - t_start

            last_state = states[-1] if states else {}
            last_state["session_id"] = sid
            last_state["total_time_ms"] = round(t_total * 1000, 1)
            last_state["avg_step_ms"] = round((t_total / max(steps, 1)) * 1000, 1)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(last_state).encode("utf-8"))

        else:
            self.send_error(404, "Not Found")

    def log_message(self, format, *args):
        # Silence verbose per-request HTTP logs in production/docker
        if "/api/step" in (args[0] if args else ""):
            return
        super().log_message(format, *args)


def run_server(port, workers):
    print("=" * 60)
    print(" ⚛️ Starting Reactor Simulation Containerized Web Service")
    print(f" Port:             {port}")
    print(f" Workers (cores):  {workers}")
    print(f" Process PID:      {os.getpid()}")
    print("=" * 60)

    # Initialize shared pool early
    get_shared_pool(workers)

    server = HTTPServer(("0.0.0.0", port), SimulationRequestHandler)

    def handle_signal(sig, frame):
        print(f"\n[Signal Handler] Caught signal {sig} ({signal.Signals(sig).name}). Shutting down gracefully...")
        shutdown_shared_pool(terminate=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        shutdown_shared_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monte Carlo Reactor Containerized Web Service")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Number of worker processes")
    args = parser.parse_args()

    run_server(args.port, args.workers)
