#!/usr/bin/env python3
"""
Калькулятор хмарної економіки (Cloud FinOps) для симулятора Монте-Карло.

Розраховує:
1. Вартість обчислень для моделей On-Demand, Reserved та Spot (Preemptible).
2. Оптимальний інтервал чекпоінту за формулою Янга/Дейлі (Young/Daly formula):
   tau = sqrt(2 * delta * M)
3. "Податок на чекпоінти" (Checkpointing Tax): накладні витрати CPU/I/O та API-викликів S3.
4. Підсумковий TCO (Total Cost of Ownership) для вибірки 10^6 та 10^7 траєкторій.

Використання:
  python3 finops_calculator.py
  python3 finops_calculator.py --samples 10000000 --workers 32 --output finops_report.json
"""

import sys
import math
import json
import argparse
from typing import Dict, Any


# Типові ринкові тарифи на базі AWS c6i.xlarge (4 vCPU, 8 GiB RAM)
DEFAULT_PRICING = {
    "instance_type": "c6i.xlarge (4 vCPU, 8 GiB RAM)",
    "vcpu": 4,
    "ram_gib": 8,
    "on_demand_hourly": 0.17,          # $0.170 / год (базовий тариф)
    "reserved_1y_hourly": 0.107,       # $0.107 / год (~37% знижка)
    "spot_hourly": 0.034,              # $0.034 / год (~80% знижка)
    "s3_put_cost_per_1000": 0.005,     # $0.005 за 1 000 PUT запитів
    "s3_storage_per_gb_month": 0.023,  # $0.023 / ГБ на місяць
    "sample_throughput_per_sec": 120.0 # траєкторій за секунду на 1 інстанс c6i.xlarge
}


def calculate_young_daly_interval(save_duration_sec: float, mean_time_between_evictions_sec: float) -> float:
    """
    Формула Янга/Дейлі: оптимальний період між чекпоінтами tau (у секундах).
      tau = sqrt(2 * delta * M)
    де:
      delta (save_duration_sec) - час запису чекпоінта на диск чи в S3 (секунди)
      M (mean_time_between_evictions_sec) - середній час життя Spot-ноди до виселення (секунди)
    """
    if save_duration_sec <= 0 or mean_time_between_evictions_sec <= 0:
        return 0.0
    return math.sqrt(2.0 * save_duration_sec * mean_time_between_evictions_sec)


def compute_tco(samples: int,
                workers: int,
                checkpoint_freq_sec: float,
                checkpoint_size_mb: float = 2.0,
                checkpoint_duration_sec: float = 1.5,
                spot_eviction_interval_hours: float = 2.0,
                pricing: Dict[str, Any] = None) -> Dict[str, Any]:
    """Розраховує повний TCO проєкту."""
    p = pricing or DEFAULT_PRICING

    # Сумарна продуктивність пулу воркерів (траєкторій / сек)
    pool_throughput = workers * p["sample_throughput_per_sec"]
    compute_duration_sec = samples / pool_throughput
    compute_duration_hours = compute_duration_sec / 3600.0

    # Оптимальний період чекпоінту
    spot_m_sec = spot_eviction_interval_hours * 3600.0
    optimal_tau_sec = calculate_young_daly_interval(checkpoint_duration_sec, spot_m_sec)

    # Кількість чекпоінтів за весь прогін
    effective_interval = checkpoint_freq_sec if checkpoint_freq_sec > 0 else optimal_tau_sec
    checkpoints_count = int(math.ceil(compute_duration_sec / max(1.0, effective_interval))) * workers

    # Витрати на S3 API (PUT requests)
    s3_put_cost = (checkpoints_count / 1000.0) * p["s3_put_cost_per_1000"]

    # Витрати на зберігання даних (протягом 1 місяця)
    storage_gb = (checkpoints_count * (checkpoint_size_mb / 1024.0))
    s3_storage_cost = storage_gb * p["s3_storage_per_gb_month"]

    # Вартість обчислень для трьох моделей
    cost_on_demand = (compute_duration_hours * workers * p["on_demand_hourly"])
    cost_reserved = (compute_duration_hours * workers * p["reserved_1y_hourly"])
    cost_spot_pure = (compute_duration_hours * workers * p["spot_hourly"])

    # У разі виселення Spot-ноди втрачається в середньому половина інтервалу чекпоінту:
    # Оверхед ретраїв при виселеннях:
    evictions_expected = (compute_duration_sec / spot_m_sec) * workers
    rerun_time_sec = evictions_expected * (effective_interval / 2.0)
    rerun_cost_spot = (rerun_time_sec / 3600.0) * workers * p["spot_hourly"]

    total_cost_spot = cost_spot_pure + rerun_cost_spot + s3_put_cost

    return {
        "parameters": {
            "samples": samples,
            "workers": workers,
            "instance_type": p["instance_type"],
            "compute_duration_sec": round(compute_duration_sec, 2),
            "compute_duration_hours": round(compute_duration_hours, 3),
            "throughput_total_samples_per_sec": pool_throughput,
            "checkpoint_interval_sec": round(effective_interval, 1),
            "optimal_young_daly_sec": round(optimal_tau_sec, 1),
            "checkpoints_count": checkpoints_count,
        },
        "costs": {
            "on_demand_usd": round(cost_on_demand, 3),
            "reserved_1y_usd": round(cost_reserved, 3),
            "spot_total_usd": round(total_cost_spot, 3),
            "breakdown_spot": {
                "compute_pure_usd": round(cost_spot_pure, 3),
                "recomputation_after_evictions_usd": round(rerun_cost_spot, 3),
                "s3_api_put_usd": round(s3_put_cost, 4),
                "s3_storage_usd": round(s3_storage_cost, 4),
            },
            "savings_spot_vs_ondemand_usd": round(cost_on_demand - total_cost_spot, 3),
            "savings_spot_percent": round((1.0 - (total_cost_spot / max(0.001, cost_on_demand))) * 100.0, 1),
        }
    }


def print_finops_report(report: Dict[str, Any]):
    p = report["parameters"]
    c = report["costs"]
    b = c["breakdown_spot"]

    print("\n" + "=" * 76)
    print("           ЗВІТ ХМАРНОЇ ЕКОНОМІКИ (CLOUD FINOPS REPORT)")
    print("=" * 76)
    print(f"Кількість траєкторій Монте-Карло : {p['samples']:,}")
    print(f"Кількість паралельних воркерів   : {p['workers']} ({p['instance_type']})")
    print(f"Сумарна продуктивність кластера  : {p['throughput_total_samples_per_sec']:,.0f} samples/sec")
    print(f"Чистий час виконання розрахунку  : {p['compute_duration_sec']:.1f} с ({p['compute_duration_hours']:.2f} год)")
    print("-" * 76)
    print("МАТЕМАТИКА ЧЕКПОІНТІВ (ФОРМУЛА ЯНГА/ДЕЙЛІ):")
    print(f"  Оптимальний інтервал (tau)     : {p['optimal_young_daly_sec']:.1f} с (~{p['optimal_young_daly_sec']/60:.1f} хв)")
    print(f"  Фактично використаний інтервал : {p['checkpoint_interval_sec']:.1f} с")
    print(f"  Кількість викликів S3 PUT      : {p['checkpoints_count']:,}")
    print("-" * 76)
    print("ПОРІВНЯННЯ МОДЕЛЕЙ ЗАКУПІВЛІ (TCO COMPARISON):")
    print(f"  1. On-Demand (100% гнучкість)  : ${c['on_demand_usd']:>8.2f}")
    print(f"  2. Reserved 1-Year (Core)      : ${c['reserved_1y_usd']:>8.2f} (економія ~37%)")
    print(f"  3. Spot / Preemptible + S3     : ${c['spot_total_usd']:>8.2f} (ЕКОНОМІЯ: {c['savings_spot_percent']}%)")
    print("     ├─ Чисті обчислення Spot    : $" + f"{b['compute_pure_usd']:>8.2f}")
    print("     ├─ Оверхед перезапусків     : $" + f"{b['recomputation_after_evictions_usd']:>8.2f}")
    print("     ├─ Податок на S3 API (PUT)  : $" + f"{b['s3_api_put_usd']:>8.4f}")
    print("     └─ Зберігання артефактів S3 : $" + f"{b['s3_storage_usd']:>8.4f}")
    print("=" * 76)
    print(f"ЧИСТА ЕКОНОМІЯ НА СПОТ-ВОРКЕРАХ  : ${c['savings_spot_vs_ondemand_usd']:,.2f} ({c['savings_spot_percent']}%)")
    print("=" * 76 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Cloud FinOps Calculator for Monte Carlo Workloads")
    parser.add_argument("--samples", type=int, default=10_000_000, help="Кількість траєкторій (за замовчуванням: 10 000 000)")
    parser.add_argument("--workers", type=int, default=16, help="Кількість паралельних воркерів")
    parser.add_argument("--checkpoint-interval", type=float, default=0.0, help="Інтервал чекпоінту в секундах (0 = за формулою Янга/Дейлі)")
    parser.add_argument("--output", type=str, default="", help="Шлях до файлу для збереження JSON-звіту")

    args = parser.parse_args()

    report = compute_tco(
        samples=args.samples,
        workers=args.workers,
        checkpoint_freq_sec=args.checkpoint_interval
    )

    print_finops_report(report)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"JSON-звіт збережено у: {args.output}")


if __name__ == "__main__":
    main()
