# Маніфести Kubernetes для Етапу 4 (Cloud & Orchestration)

> **Декларація курсу.** Матеріали курсу «Грід-системи та технології хмарних обчислень».

Даний каталог містить готові декларативні маніфести Kubernetes для розгортання симулятора Монте-Карло (образ `reactor-web:latest`, зібраний на Етапі 3).

## Структура файлів

- `deployment.yaml` — базовий маніфест веб-сервісу з лімітом пам'яті 512Mi (демонструє кейс OOMKilled під час навантаження).
- `deployment-fixed.yaml` — виправлений маніфест веб-сервісу зі збільшеним лімітом пам'яті 1Gi (стабільна робота під високим навантаженням).
- `service.yaml` — мережева абстракція: внутрішній `ClusterIP` (DNS-ім'я всередині кластера) та зовнішній `NodePort` (`30080`).
- `job-batch.yaml` — базовий маніфест пакетного навантаження (демонструє кейс аварії Job, FailureTarget та вичерпання backoffLimit).
- `job-batch-fixed.yaml` — виправлений маніфест пакетного навантаження (1Gi RAM, коректні ключі API) для успішного прогону (4/4 completions).
- `job-chaos-retry.yaml` — демонстрація механізму Exponential Backoff і ретраїв при падінні подів.

## Швидкий запуск

### 1. Збірка та імпорт образу в кластер

```bash
# 1. Збірка образу етапу 3 (якщо ще не зібрано)
docker build -t reactor-web:latest ../docker-web

# 2. Завантаження образу в локальний кластер без push у Docker Hub:
# Для Minikube:
minikube image load reactor-web:latest

# Для k3s:
docker save reactor-web:latest | sudo k3s ctr images import -

# 3. Активація збору метрик (Metrics Server у Minikube для уникнення помилок 'Metrics API not available'):
minikube addons enable metrics-server
```

### 2. Розгортання Web-сервісу (Deployment + Service)

```bash
# Застосувати маніфести
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# Перевірка статусу подів та ендпоінтів
kubectl get pods -l app=reactor-web -o wide
kubectl get svc reactor-web-service

# Перевірка метрик навантаження
kubectl top nodes
kubectl top pods

# Доступ до дашборду:
# На Linux:
curl http://$(minikube ip):30080/api/health
# Або універсально (Linux / Windows WSL2):
kubectl port-forward svc/reactor-web-service 8080:8080
# Відкрити у браузері: http://localhost:8080
```

### 3. Запуск пакетного розрахунку Монте-Карло (Job) та збереження результатів

```bash
kubectl apply -f job-batch-fixed.yaml

# Спостереження за паралельним виконанням
kubectl get jobs -w
kubectl get pods -l workload=monte-carlo-trial

# Перегляд логів розрахунку
kubectl logs -l workload=monte-carlo-trial --tail=50 -f

# Найпростіший шлях експорту JSON-результатів бенчмарку (без монтування Persistent Volumes):
kubectl logs -l job-name=powergrid-batch > benchmark_k8s.json
# або для поточного маніфесту реактора:
kubectl logs -l workload=monte-carlo-trial --tail=50 > benchmark_k8s.json
```
