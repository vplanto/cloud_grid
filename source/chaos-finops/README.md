# Стенд Chaos Engineering, Jaeger OpenTracing та FinOps (Етап 5)

> **Декларація курсу.** Матеріали курсу «Грід-системи та технології хмарних обчислень».

Даний каталог містить програмний інструментарій та декларативні маніфести для виконання завдань **Етапу 5 (Chaos & FinOps)**.

## Вміст каталогу

- `jaeger.yaml` — маніфест Kubernetes для розгортання бекенду трасування Jaeger (UI порт `16686`, OTLP gRPC порт `4317`).
- `docker-compose.yml` — запуск Jaeger та воркера однією командою у середовищі Docker.
- `tracer.py` — бібліотека інтеграції з OpenTelemetry з підтримкою W3C TraceContext (`traceparent`) та безпечним fallback-режимом.
- `chaos_experiment.py` — сценарії хаос-тестування: `poison-pill` (каскадний OOM та DLQ), `retry-storm` (Thundering Herd vs Circuit Breaker), `spot` (SIGTERM + чекпоінти), `latency` (P50/P90/P99).
- `finops_calculator.py` — розрахунок вартості обчислень (On-Demand, Reserved, Spot), формула Янга/Дейлі, S3 API tax та TCO.
- `requirements.txt` — залежності для OpenTelemetry та експортерів.

## Швидкий запуск експериментів

### 1. Розгортання Jaeger у Kubernetes або Docker

```bash
# Варіант A: У кластері Kubernetes (Minikube / k3s)
kubectl apply -f jaeger.yaml
kubectl port-forward svc/jaeger-service 16686:16686

# Варіант B: Через Docker Compose
docker compose up -d jaeger
```
Відкрийте веб-інтерфейс Jaeger у браузері: `http://localhost:16686`.

### 2. Запуск хаос-сценаріїв

```bash
# Сценарій 1: "Отруйна пігулка" (Poison Pill), каскадний OOM та порятунок через DLQ
python3 chaos_experiment.py poison-pill            # CrashLoopBackOff кластера
python3 chaos_experiment.py poison-pill --protect  # Ізоляція в Dead Letter Queue

# Сценарій 2: Шторм ретраїв (Retry Storm) vs Full Jitter + Circuit Breaker
python3 chaos_experiment.py retry-storm --strategy naive           # Thundering herd
python3 chaos_experiment.py retry-storm --strategy jitter-breaker  # Стійка система

# Сценарій 3: Симуляція виселення Spot-вузла та Graceful Checkpointing
python3 chaos_experiment.py spot --trials 1000 --checkpoint-interval 200

# Сценарій 4: Мережевий джитер, Long-Tail затримка та перцентилі P50/P90/P99
python3 chaos_experiment.py latency --samples 200 --chaos-pct 3.0
```

### 3. Розрахунок TCO та хмарної оптимізації (FinOps)

```bash
python3 finops_calculator.py --samples 10000000 --workers 16 --output finops_report.json
```
