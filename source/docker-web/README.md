# Референтний сервіс симуляції (Етап 3: Docker & Web)

Навчальний модуль демонструє контейнеризацію обчислювального рушія Монте-Карло, REST API для оркестрації та інтерактивний браузерний дашборд.

---

## 1. Швидкий старт

### Збірка та запуск через Docker Compose
```bash
cd source/docker-web
docker compose up --build
```

Сервіс буде доступний за адресою:
- **Web UI & Dashboard:** [http://localhost:8080](http://localhost:8080)
- **Health Check:** `curl http://localhost:8080/api/health`
- **System Metrics:** `curl http://localhost:8080/api/metrics`

### Запуск у фоновому режимі (detached)
```bash
docker compose up -d
docker compose ps
docker compose logs -f reactor-sim
```

### Зупинка та очищення
```bash
docker compose down
```

---

## 2. Автономний запуск через Docker CLI

```bash
# Збірка образу
docker build -t reactor-sim:latest .

# Запуск з лімітами cgroups (2 ядра, 512MB RAM)
docker run -d --name reactor-app \
  -p 8080:8080 \
  --cpus="2.0" \
  --memory="512m" \
  reactor-sim:latest

# Перевірка утилізації ресурсів у реальному часі
docker stats reactor-app
```

---

## 3. REST API Специфікація

| Метод | Ендпоінт | Опис | Параметри запиту (JSON) |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | WebGL/Canvas UI дашборд | — |
| `GET` | `/api/health` | Liveness/Readiness перевірка стану | — |
| `GET` | `/api/metrics` | Метрики сесій, PID та воркерів | — |
| `POST` | `/api/reset` | Скидання стану симуляції | `{"fuel_mass": 50, "n_fast": 350000, "n_slow": 150000}` |
| `POST` | `/api/step` | Виконання 1 кроку симуляції | — |
| `POST` | `/api/batch` | Пакетне виконання N кроків | `{"steps": 10}` |

### Приклад виконання батчу через curl:
```bash
curl -X POST http://localhost:8080/api/batch \
  -H "Content-Type: application/json" \
  -H "X-Simulation-Session: benchmark_session" \
  -d '{"steps": 15}'
```
