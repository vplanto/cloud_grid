# Грід-системи та технології хмарних обчислень

> **Декларація курсу.** Академічна доброчесність та авторство матеріалів — у [DISCLAIMER.md](DISCLAIMER.md).

Головна сторінка навчального курсу «Грід-системи та технології хмарних обчислень».

---

## Про курс та ідеологію

Курс про **розподілені системи** — відповідь на те, чому один сервер більше не тягне.

* **Контекст:** від ООП на одній машині — до кластерів, контейнерів, хмар.
* **Головний біль:** спільний mutable-стан у мережі → race conditions, затримки, розсинхрон.
* **Мета:** проєктувати горизонтально масштабовані Cloud/Grid-архітектури; зрозуміти, навіщо потрібні stateless і реактивні підходи.

**Навчальний формат:** 11 пар лекцій + 10 пар лабораторних. На лабораторних **5 пар — майстер-класи** (демонстрація викладача + паралельна робота студентів) і **5 пар — захисти** (демо, бенчмарк, код-рев'ю за [регламентом](./n00_self_work.md)).

**Наскрізна нитка курсу** — метод Монте-Карло на різних рівнях абстракції ([деталі у вступі](./00_intro.md#наша-мета-відтворити-історію-на-сучасних-технологіях)):

| Етап курсу | Де запускаємо | Технологія |
| :---: | :--- | :--- |
| **1** | Локально на ноутбуці | MIMD на CPU (`Pool.map`), benchmark |
| **2** | Аналог Гріда | **Ray** / кластер без Docker, benchmark |
| **3** | У Docker | контейнер + веб/API, `docker-compose`, benchmark |
| **4** | Аналог K8s | **Kubernetes**, benchmark |
| **5** | Chaos & FinOps | Jaeger, відмовостійкість, TCO |

---

## 1. Лекційні матеріали (11 пар)

*Усі лекції 0–10 розроблені та доступні за посиланнями нижче.*

| Пара | Лекція | Зміст | Етап курсу |
| :---: | :--- | :--- | :---: |
| **1** | [Лекція 0: Вступ до курсу та еволюція абстракцій](./00_intro.md) | Манхеттенський проєкт, Монте-Карло, ENIAC → мейнфрейми → Грід → хмари; два MC-патерни (реактор / мережа) | — |
| **2** | [Лекція 1: Таксономія Фліна](./01_flynn_taxonomy.md) | SISD / SIMD / MISD / MIMD; ПК, GPU, мейнфрейми; trade-offs архітектур | огляд |
| **3** | [Лекція 2: Моделі обчислень — HPC/Grid (Batch) vs Cloud (Interactive) & алгоритми планування](./02_hpc_grid_vs_cloud.md) | HPC (утилізація заліза 100%) vs Web/Cloud (P99 latency, еластичність); DAG задач; DRF у Slurm/PBS vs bin-packing у K8s; **trade-off:** макс. утилізація (Grid) vs прогнозованість затримки (Cloud) | 2 |
| **4** | [Лекція 3: Механіка ізоляції — гіпервізори (VM) vs контейнеризація (cgroups & namespaces)](./03_isolation_mechanics.md) | Еволюція фізичний сервер → VM → контейнер; гіпервізори Type-1/2 vs namespaces і cgroups v2; **trade-off:** повна ізоляція й оверхед (VM) vs легковажність і спільне ядро (Containers) | 2–3 |
| **5** | [Лекція 4: Архітектура Multi-Tenant систем (IaaS, PaaS, SaaS) & проблема Noisy Neighbor](./04_multitenancy_noisy_neighbor.md) | Shared vs Dedicated tenancy; Tenant Gateways, ізоляція даних; Rate Limiting (Token Bucket, Leaky Bucket); **trade-off:** економія ресурсів і Noisy Neighbor vs дорога hard isolation | 3–4 |
| **6** | [Лекція 5: Хмарні мережеві абстракції, API Gateways & Service Mesh](./05_networking_mesh.md) | Взаємодія Pod-to-Pod; API Gateway (маршрутизація, авторизація); sidecar proxy, mTLS, traffic splitting, circuit breaking; **trade-off:** прозорість і безпека vs затримка та CPU-оверхед проксі | 4 |
| **7** | [Лекція 6: Архітектура розподіленого зберігання даних & Consistent Hashing](./06_distributed_storage_hashing.md) | Block (EBS) / File (NFS) / Object (S3, immutability); шардинг RDBMS vs NoSQL; consistent hashing з віртуальними вузлами; **trade-off:** ACID vs BASE / горизонтальне масштабування | 4 |
| **8** | [Лекція 7: Декларативна оркестрація (Kubernetes Control Plane) & ресурсна модель](./07_k8s_orchestration_resources.md) | Декларативна модель vs імперативні скрипти; etcd, reconciliation loop; Pod lifecycle; QoS (Guaranteed, Burstable, BestEffort); **trade-off:** self-healing vs evictions під node-pressure | 4 |
| **9** | [Лекція 8: Системна спостережуваність (Observability) & troubleshooting розподілених відмов](./08_observability_troubleshooting.md) | P50/P90/P99; distributed tracing (Jaeger: spans, baggage); ELK / Graylog; ImagePullBackOff, CrashLoopBackOff, Exit 137 (OOM); **trade-off:** повна прозорість vs накладні витрати на мережу й зберігання | 4 |
| **10** | [Лекція 9: Безстановість (Stateless), Event-Driven Architecture & Serverless (FaaS)](./09_stateless_eda_serverless.md) | Гарантії доставки подій (at-most/least/exactly-once); Kafka, RabbitMQ; FaaS і cold start; **trade-off:** нульова вартість у простої vs cold start latency | 4–5 |
| **11** | [Лекція 10: FinOps, Resilience Engineering (Chaos) & підсумковий архітектурний синтез](./10_finops_resilience_synthesis.md) | Capacity planning, Spot/Preemptible, TCO; Chaos Engineering (Chaos Mesh, Toxiproxy); синтез 5 етапів курсу — імперативне ядро, ООП-модулі, контейнери, stateless-код, AI-інструменти | — |

---

## 2. Лабораторний блок (10 пар)

**Перед першою лабораторною:** [Практика 0 — Agentic LLM (як працювати з ШІ-агентом)](./p00_agentic_llm.md) — документо-орієнтований цикл, демо на [Google Antigravity](https://antigravity.google/).

**5 майстер-класів + 5 захистів.** На кожному майстер-класі два паралельні треки:

- **Демонстрація викладача** — [реактор / нейтрони](./p01_neutron_monte_carlo.md) (`source/mimd-pc/app.py`)
- **Самостійний проєкт** — [IEEE-118 PowerGrid](./n01_power_grid_project.md)

| Пара | Тип пари | Демонстрація викладача (реактор) | Самостійний проєкт (IEEE-118) | Контроль |
| :---: | :---: | :--- | :--- | :---: |
| **0** | *(до пари 1)* | [Практика 0: Agentic LLM](./p00_agentic_llm.md) — роль·контекст·мета, PLAN → approve → код | Налаштування workspace, `docs/work/PLAN.md` для етапу 1 | — |
| **1** | майстер-клас 1 | [Практика 1: симуляція ділення нейтронів](./p01_neutron_monte_carlo.md) — **Етап 1 (MIMD):** CPU (`multiprocessing.Pool`, GIL, 100% CPU benchmark) | Парсинг топології IEEE-118, однопотоковий `run_trial()` | — |
| **2** | майстер-клас 2 | [Практика 2: Ray-кластер (1 head + 2 workers)](./p02_ray_grid.md) — **Етап 2 (Grid):** NumPy + `run.py client/head/load`, batch без Docker | Векторизація каскадного розрахунку на графі, підготовка локального Ray-кластера | — |
| **3** | **захист 1** | — | Захист **етапів 1–2:** `grid-mimd/app.py`, speedup-бенчмарк, Ray | **КТ 1** |
| **4** | майстер-клас 3 | **Етап 3 (Docker & Web):** контейнеризація воркерів у `Dockerfile`, WebGL Dashboard / REST API | Контейнеризація сервісів, `docker-compose.yml`, API | — |
| **5** | **захист 2** | — | Захист **етапу 3:** відтворюваний запуск `docker-compose up` | **КТ 2** |
| **6** | майстер-клас 4 | **Етап 4 (Kubernetes):** Job/Deployment з образу етапу 3, retries / heartbeats | Запуск обчислень IEEE-118 у K8s-кластері (minikube/kind) | — |
| **7** | **захист 3** | — | Захист **етапу 4:** K8s-запуск, аналіз продуктивності | **КТ 3** |
| **8** | майстер-клас 5 | **Етап 5 (Chaos & FinOps):** симуляція аварій (SIGKILL воркерів, OOM / Exit Code 137), Jaeger OpenTracing | Впровадження відмовостійкості, профілювання P99 затримки | — |
| **9** | **захист 4** | — | Захист **етапу 5:** стійкість при вбивстві нод, аналіз логів і спанів | **КТ 4** |
| **10** | **фінал** | — | Підсумковий захист: повний Git-репозиторій, FinOps-розрахунок, архітектурна співбесіда | **залік** |

---

## 3. Самостійна робота

1. [Регламент: Загальні вимоги до виконання та захисту робіт](./n00_self_work.md)
2. [Наскрізний проєкт: Симуляція стійкості енергосистеми IEEE-118 методом Монте-Карло](./n01_power_grid_project.md)
3. [Програма СРС (80 годин) та рекомендовані міжнародні курси](./n02_recommended_courses.md)

**Контрольні точки проєкту** (здача на лабораторних парах 3, 5, 7, 9; залік — пара 10):

| Етап проєкту | Лаб. пара | Результат |
| :--- | :---: | :--- |
| **1.** MIMD на CPU — `multiprocessing`, однопотоковий і паралельний `run_trial()` | 3 (КТ 1) | `grid-mimd/app.py`, speedup, звірка з PowerGraph |
| **2.** Векторизація (NumPy) + Ray без Docker | 3 (КТ 1) | прискорений каскад, локальний Ray-кластер |
| **3.** Docker + веб-сервіси (dashboard, API) | 5 (КТ 2) | `docker-compose up` «з коробки» |
| **4.** Kubernetes (Job/Deployment) | 7 (КТ 3) | K8s-запуск, аналіз throughput |
| **5.** Chaos & FinOps — відмовостійкість, Jaeger, P99 | 9 (КТ 4) | стійкість при падінні нод, логи й спани |
| **Фінал.** Повний репозиторій + архітектурна співбесіда | 10 | залік |

Демонстраційний код реактора: [практика 1](./p01_neutron_monte_carlo.md) — `source/mimd-pc/`; [практика 2](./p02_ray_grid.md) — `source/ray-grid/`. Датасет і скрипти PowerGraph — у `source/dataset_scripts/`.

---

## Пов'язані курси

Конкретні лекції з інших дисциплін програми згадані в тексті відповідних розділів. Загальний контекст:

| Курс | Сторінка | Перетин з Cloud/Grid |
| :--- | :--- | :--- |
| Прикладне функціональне програмування та реактивні системи | [functional_programming](https://vplanto.github.io/functional_programming/) | immutability, чисті функції, stateless-сервіси |
| Java, 2-й семестр | [02_semester](https://vplanto.github.io/java/02_semester/) | розподілені системи, відмови, Docker |
| Основи інтернет-технологій (Web Engineering) | [java_script](https://vplanto.github.io/java_script/) | браузерний рендеринг, HTTP, dashboard |

---

*Ознайомтеся перед початком:* [Disclaimer](./DISCLAIMER.md)
