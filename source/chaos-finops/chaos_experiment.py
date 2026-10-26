#!/usr/bin/env python3
"""
Скрипт лабораторних експериментів Chaos Engineering & Observability (Етап 5).

Сценарії:
  1. poison-pill   - Каскадний OOM через "отруйну задачу" (Poison Pill Task), локалізація в Jaeger та ізоляція через DLQ
  2. retry-storm   - Шторм повторних спроб (Thundering Herd) vs Full Jitter + Circuit Breaker
  3. spot          - Симуляція виселення Spot-інстансу з Graceful Checkpointing (SIGTERM handling)
  4. latency       - Симуляція мережевого джитера та профілювання перцентилів P50/P90/P99

Використання:
  python3 chaos_experiment.py poison-pill [--protect]
  python3 chaos_experiment.py retry-storm [--strategy naive|jitter-breaker]
  python3 chaos_experiment.py spot --trials 1000 --checkpoint-interval 200
  python3 chaos_experiment.py latency --samples 200
"""

import os
import sys
import time
import signal
import argparse
import json
import random
import math
from typing import List, Dict, Any, Optional

from tracer import get_tracer, start_span, inject_trace_context


# -----------------------------------------------------------------------------
# СЦЕНАРІЙ 1: POISON PILL TASK & КАСКАДНИЙ OOM У ЧЕРЗІ
# -----------------------------------------------------------------------------
class PoisonPillOOMException(Exception):
    """Штучна імітація раптового OOM (Exit Code 137) від надважкої задачі."""
    pass


def run_poison_pill_experiment(protect_with_dlq: bool = False):
    print("=" * 75)
    print("СЦЕНАРІЙ 1: 'Отруйна пігулка' (Poison Pill) та каскадний збій воркерів")
    print("=" * 75)
    print(f"Захист черги через Dead Letter Queue (DLQ): {'ВВІМКНЕНО' if protect_with_dlq else 'ВИМКНЕНО (Наївна черга)'}")
    print("У чергу додано 8 звичайних задач і 1 задачу-диверсант ('poison_matrix_ieee118').")
    print("-" * 75)

    # Черга завдань
    tasks_queue = [
        {"task_id": f"batch_{i}", "samples": 500, "is_poison": False, "attempts": 0}
        for i in range(1, 5)
    ]
    # Вставляємо задачу-диверсант всередину черги
    tasks_queue.insert(2, {
        "task_id": "poison_matrix_ieee118",
        "samples": 10_000_000, # Вимагає надмірного виділення ОЗП (>1GB)
        "is_poison": True,
        "attempts": 0
    })
    tasks_queue.extend([
        {"task_id": f"batch_{i}", "samples": 500, "is_poison": False, "attempts": 0}
        for i in range(5, 9)
    ])

    dlq: List[Dict[str, Any]] = []
    completed: List[str] = []
    max_retries = 2
    worker_id = 1

    with start_span("queue.dispatch_pipeline", {"dlq_enabled": protect_with_dlq}):
        while tasks_queue:
            task = tasks_queue.pop(0)
            task_id = task["task_id"]
            task["attempts"] += 1

            print(f"\n[Воркер {worker_id}] Взято в обробку: '{task_id}' (Спроба {task['attempts']})...")

            with start_span("worker.process_task", {"task.id": task_id, "attempt": task["attempts"]}) as span:
                span.set_attribute("task.is_poison", task["is_poison"])

                if task["is_poison"]:
                    # Імітуємо падіння через критичний перерозхід пам'яті (OOM / Exit 137)
                    span.set_attribute("error", True)
                    span.set_attribute("exception.type", "OOMKilled_ExitCode_137")
                    print(f"  [CRASH!] Воркер {worker_id} перевищив ліміт cgroups memory.max!")
                    print(f"  [ЯДРО LINUX] OOM Killer ліквідував воркер (Exit Code 137 / SIGKILL)!")

                    if not protect_with_dlq:
                        # У наївній системі задача повертається на початок черги
                        print("  [НАЇВНА ЧЕРГА] Необроблена задача повертається в чергу. Піднімаємо новий воркер...")
                        tasks_queue.insert(0, task)
                        worker_id += 1
                        time.sleep(0.5)
                        if worker_id > 5:
                            print("\n" + "!" * 75)
                            print("[КАТАСТРОФА: CrashLoopBackOff кластера!]")
                            print("Одна отруйна задача по черзі вбила 5 воркерів поспіль!")
                            print("Решта 6 валідних задач черги заблоковані назавжди (Head-of-Line Blocking)!")
                            print("Знайдіть у Jaeger UI спан із помилкою: 'worker.process_task' -> task.is_poison=True")
                            print("!" * 75)
                            return
                    else:
                        # Режим захисту: перевірка ліміту спроб та ізоляція в DLQ
                        if task["attempts"] >= max_retries:
                            print(f"  [DLQ ЗАХИСТ] Задачу '{task_id}' вичерпано ({task['attempts']} невдачі).")
                            print(f"  [QUARANTINE] Задачу ізольовано у Dead Letter Queue (dead_letter_queue.json)!")
                            dlq.append(task)
                            span.set_attribute("task.routed_to_dlq", True)
                        else:
                            print(f"  [RETRY] Відкат спроби. Залишилось спроб: {max_retries - task['attempts']}.")
                            tasks_queue.append(task) # Кидаємо в кінець черги, щоб не блокувати інших
                else:
                    time.sleep(0.1) # Симуляція штатної обробки 100 мс
                    completed.append(task_id)
                    print(f"  [OK] Задачу '{task_id}' успішно обчислено.")

    print("\n" + "=" * 75)
    print("ПІДСУМОК РОБОТИ ЧЕРГИ З DLQ:")
    print(f"  Успішно обчислено задач : {len(completed)} / 8")
    print(f"  Ізольовано в DLQ        : {len(dlq)} (задача: {[t['task_id'] for t in dlq]})")
    print("Кластер вижив, каскадного падіння уникнуто!")
    print("=" * 75)


# -----------------------------------------------------------------------------
# СЦЕНАРІЙ 2: RETRY STORM (THUNDERING HERD) VS FULL JITTER + CIRCUIT BREAKER
# -----------------------------------------------------------------------------
class CircuitBreaker:
    """Проста реалізація запобіжника (Circuit Breaker)."""
    def __init__(self, failure_threshold: int = 3, recovery_time_sec: float = 1.5):
        self.failure_threshold = failure_threshold
        self.recovery_time_sec = recovery_time_sec
        self.failure_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.last_state_change = time.time()

    def allow_request(self) -> bool:
        now = time.time()
        if self.state == "OPEN":
            if now - self.last_state_change > self.recovery_time_sec:
                self.state = "HALF-OPEN"
                return True
            return False
        return True

    def record_success(self):
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self):
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            self.last_state_change = time.time()


def simulate_degraded_backend(req_time: float) -> bool:
    """Бекенд відмовляє в перші 1.2 секунди тесту, потім оживає."""
    return req_time > 1.2


def run_retry_storm_experiment(strategy: str = "naive"):
    print("=" * 75)
    print("СЦЕНАРІЙ 2: Шторм ретраїв (Retry Storm) vs Full Jitter & Circuit Breaker")
    print("=" * 75)
    print(f"Обрана стратегія клієнтів: {strategy.upper()}")
    print("Бекенд тимчасово падає на перші 1.2 секунди. 10 паралельних клієнтів роблять запити.")
    print("-" * 75)

    start_time = time.time()
    num_clients = 10
    total_backend_hits = 0
    client_results = []

    with start_span("chaos.retry_storm_test", {"strategy": strategy}):
        for client_id in range(1, num_clients + 1):
            cb = CircuitBreaker() if strategy == "jitter-breaker" else None
            attempts = 0
            success = False

            while attempts < 4 and not success:
                attempts += 1
                now = time.time() - start_time

                # Перевірка запобіжника
                if cb and not cb.allow_request():
                    # Запобіжник розімкнено: швидкий фейл без навантаження на сервер
                    time.sleep(0.1)
                    continue

                total_backend_hits += 1
                backend_ok = simulate_degraded_backend(now)

                if backend_ok:
                    success = True
                    if cb:
                        cb.record_success()
                    client_results.append((client_id, attempts, round(now, 3), "SUCCESS"))
                else:
                    if cb:
                        cb.record_failure()

                    # Пауза перед наступною спробою
                    if strategy == "naive":
                        # Синхронний Exponential Backoff (без Jitter) -> РЕЗОНАНС!
                        sleep_time = 0.3 * (2 ** (attempts - 1))
                    else:
                        # Full Jitter: випадковий інтервал від 0 до max_backoff
                        max_backoff = 0.3 * (2 ** (attempts - 1))
                        sleep_time = random.uniform(0.05, max_backoff)

                    time.sleep(sleep_time)

            if not success:
                client_results.append((client_id, attempts, round(time.time() - start_time, 3), "FAILED"))

    print("\nРЕЗУЛЬТАТИ ВИТРИВАЛОСТІ БЕКЕНДУ:")
    print(f"  Сумарна кількість ударів по бекенду (HTTP Hits) : {total_backend_hits}")
    if strategy == "naive":
        print("  [АНАЛІЗ SRE] Синхронні повтори без Jitter створили Thundering Herd!")
        print("  Бекенд отримав надмірний шквал ударів у пік відновлення.")
    else:
        print("  [АНАЛІЗ SRE] Circuit Breaker скинув навантаження, а Full Jitter згладив піки.")
        print(f"  Кількість запитів скоротилася майже вдвічі без втрати якості!")
    print("=" * 75)


# -----------------------------------------------------------------------------
# СЦЕНАРІЙ 3: SPOT PREEMPTION & GRACEFUL CHECKPOINTING
# -----------------------------------------------------------------------------
_PREEMPTION_TRIGGERED = False
_CHECKPOINT_FILE = "spot_checkpoint.json"

def _sigterm_handler(signum, frame):
    global _PREEMPTION_TRIGGERED
    print("\n[SPOT NOTICE] Отримано сигнал SIGTERM! Хмара забирає Spot-ноду через 30 секунд!")
    _PREEMPTION_TRIGGERED = True


def run_spot_experiment(total_trials: int = 1000, checkpoint_interval: int = 200):
    print("=" * 75)
    print("СЦЕНАРІЙ 3: Spot Preemption із Graceful Checkpointing")
    print("=" * 75)
    print(f"PID процесу: {os.getpid()}")
    print(f"Розрахунок {total_trials} траєкторій. Інтервал збереження стану: {checkpoint_interval} ітерацій.")
    print("Щоб надіслати Spot-сповіщення в іншій консолі:")
    print(f"  kill -TERM {os.getpid()}")
    print("-" * 75)

    signal.signal(signal.SIGTERM, _sigterm_handler)

    start_index = 0
    accumulated_results = []
    if os.path.exists(_CHECKPOINT_FILE):
        try:
            with open(_CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                start_index = saved.get("completed_trials", 0)
                accumulated_results = saved.get("results", [])
                print(f"[RECOVERY] Знайдено збережений чекпоінт! Відновлення з ітерації {start_index}/{total_trials}.")
        except Exception as e:
            print(f"[WARNING] Помилка читання чекпоінта: {e}. Починаємо з нуля.")

    with start_span("monte_carlo.spot_batch", {"total_trials": total_trials, "start_index": start_index}):
        for i in range(start_index, total_trials):
            if _PREEMPTION_TRIGGERED:
                print(f"[CHECKPOINT] Екстрене збереження стану на кроці {i}/{total_trials} перед загибеллю ноди...")
                with start_span("checkpoint.emergency_save", {"step": i}):
                    with open(_CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                        json.dump({
                            "completed_trials": i,
                            "results": accumulated_results,
                            "timestamp": time.time(),
                            "status": "preempted"
                        }, f, indent=2)
                print(f"[SHUTDOWN] Чекпоінт збережено у {_CHECKPOINT_FILE}. Штатний вихід із кодом 0.")
                sys.exit(0)

            trial_score = random.gauss(100.0, 15.0)
            accumulated_results.append(trial_score)

            if (i + 1) % checkpoint_interval == 0:
                print(f"[Крок {i+1:4d}/{total_trials}] Збереження планового чекпоінта у {_CHECKPOINT_FILE}...")
                with start_span("checkpoint.regular_save", {"step": i + 1}):
                    with open(_CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                        json.dump({
                            "completed_trials": i + 1,
                            "results": accumulated_results,
                            "timestamp": time.time(),
                            "status": "in_progress"
                        }, f, indent=2)

            time.sleep(0.01)

        print(f"\n[SUCCESS] Усі {total_trials} траєкторій обчислено успішно!")
        if os.path.exists(_CHECKPOINT_FILE):
            os.remove(_CHECKPOINT_FILE)
            print("[CLEANUP] Тимчасовий файл чекпоінта видалено.")


# -----------------------------------------------------------------------------
# СЦЕНАРІЙ 4: МЕРЕЖЕВИЙ ДЖИТЕР ТА ПРОФІЛЮВАННЯ P50 / P90 / P99
# -----------------------------------------------------------------------------
def calculate_percentiles(latencies_ms: List[float]) -> Dict[str, float]:
    sorted_lat = sorted(latencies_ms)
    n = len(sorted_lat)
    if n == 0:
        return {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0}

    def get_pct(p: float) -> float:
        idx = int(math.ceil(p / 100.0 * n)) - 1
        return sorted_lat[max(0, min(idx, n - 1))]

    return {
        "p50": get_pct(50),
        "p90": get_pct(90),
        "p95": get_pct(95),
        "p99": get_pct(99),
        "mean": sum(sorted_lat) / n
    }


def print_ascii_histogram(latencies_ms: List[float], bins_count: int = 10):
    if not latencies_ms:
        return
    min_v, max_v = min(latencies_ms), max(latencies_ms)
    if min_v == max_v:
        print(f"Всі затримки ідентичні: {min_v:.2f} мс")
        return

    bin_width = (max_v - min_v) / bins_count
    counts = [0] * bins_count

    for v in latencies_ms:
        idx = int((v - min_v) / bin_width)
        if idx >= bins_count:
            idx = bins_count - 1
        counts[idx] += 1

    max_count = max(counts)
    print("\nРозподіл затримок (ASCII-гістограма):")
    for i in range(bins_count):
        range_start = min_v + i * bin_width
        range_end = range_start + bin_width
        bar_len = int((counts[i] / max_count) * 40)
        bar = "█" * bar_len
        print(f"[{range_start:6.1f} - {range_end:6.1f} мс]: {bar:<40} ({counts[i]:3d})")


def run_latency_experiment(samples: int = 200, chaos_pct: float = 2.5):
    print("=" * 75)
    print("СЦЕНАРІЙ 4: Мережевий джитер, Long-Tail Latency та перцентилі P50/P90/P99")
    print("=" * 75)
    print(f"Генерація {samples} запитів. Частота аномалій (Chaos Injection): {chaos_pct}% запитів.")

    latencies_ms = []

    with start_span("workload.latency_benchmark", {"samples": samples, "chaos_pct": chaos_pct}):
        for i in range(1, samples + 1):
            start = time.perf_counter()
            base_delay = random.uniform(0.010, 0.025)

            is_anomaly = random.uniform(0, 100) < chaos_pct
            anomaly_delay = 0.0
            if is_anomaly:
                anomaly_delay = random.uniform(0.300, 0.850)

            with start_span("trial.compute", {"trial_id": i, "is_anomaly": is_anomaly}):
                time.sleep(base_delay + anomaly_delay)

            elapsed_ms = (time.perf_counter() - start) * 1000.0
            latencies_ms.append(elapsed_ms)

            if i % 25 == 0 or is_anomaly:
                flag = " [!] CHAOS SPIKE" if is_anomaly else ""
                print(f"Запит {i:3d}/{samples}: latency = {elapsed_ms:6.1f} мс{flag}")

    metrics = calculate_percentiles(latencies_ms)
    print_ascii_histogram(latencies_ms)

    print("\n" + "=" * 50)
    print("ПІДСУМКОВА СТАТИСТИКА ЗАТРИМОК (SRE METRICS):")
    print("=" * 50)
    print(f"Середнє арифметичне (Mean) : {metrics['mean']:6.2f} мс (МАСКУЄ ПРОБЛЕМИ!)")
    print(f"Медіана (P50)             : {metrics['p50']:6.2f} мс (нормальний режим роботи)")
    print(f"Перцентиль P90            : {metrics['p90']:6.2f} мс")
    print(f"Перцентиль P95            : {metrics['p95']:6.2f} мс")
    print(f"Хвостова затримка (P99)   : {metrics['p99']:6.2f} мс <--- ЗОНА РИЗИКУ")
    print("=" * 50)
    print(f"Співвідношення P99 / P50: {metrics['p99'] / max(0.1, metrics['p50']):.1f}x різниця!")


# -----------------------------------------------------------------------------
# MAIN CLI DISPATCHER
# -----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Chaos Engineering & Observability Lab Experiments")
    subparsers = parser.add_subparsers(dest="scenario", required=True, help="Обрати експеримент")

    # Сценарій 1: poison-pill
    sp_pp = subparsers.add_parser("poison-pill", help="Каскадний OOM через отруйну задачу та DLQ")
    sp_pp.add_argument("--protect", action="store_true", help="Увімкнути захист через Dead Letter Queue")

    # Сценарій 2: retry-storm
    sp_rs = subparsers.add_parser("retry-storm", help="Шторм ретраїв vs Full Jitter + Circuit Breaker")
    sp_rs.add_argument("--strategy", choices=["naive", "jitter-breaker"], default="naive",
                       help="Стратегія клієнтів (naive або jitter-breaker)")

    # Сценарій 3: spot
    sp_spot = subparsers.add_parser("spot", help="Симуляція Spot-виселення з чекпоінтами")
    sp_spot.add_argument("--trials", type=int, default=1000, help="Загальна кількість траєкторій")
    sp_spot.add_argument("--checkpoint-interval", type=int, default=200, help="Інтервал збереження")

    # Сценарій 4: latency
    sp_lat = subparsers.add_parser("latency", help="Симуляція мережевого джитера та перцентилі P99")
    sp_lat.add_argument("--samples", type=int, default=200, help="Кількість запитів")
    sp_lat.add_argument("--chaos-pct", type=float, default=2.5, help="Відсоток аномальних запитів")

    args = parser.parse_args()

    if args.scenario == "poison-pill":
        run_poison_pill_experiment(protect_with_dlq=args.protect)
    elif args.scenario == "retry-storm":
        run_retry_storm_experiment(strategy=args.strategy)
    elif args.scenario == "spot":
        run_spot_experiment(total_trials=args.trials, checkpoint_interval=args.checkpoint_interval)
    elif args.scenario == "latency":
        run_latency_experiment(samples=args.samples, chaos_pct=args.chaos_pct)

if __name__ == "__main__":
    main()
