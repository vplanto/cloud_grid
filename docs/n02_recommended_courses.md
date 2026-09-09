# Програма самостійної роботи (СРС) та рекомендовані курси

> **Декларація курсу.** Академічна доброчесність та авторство матеріалів — у [DISCLAIMER.md](DISCLAIMER.md).

Згідно з навчальним планом дисципліни обсяг самостійної роботи здобувача становить **80 академічних годин** (із загальних 120 годин / 4 кредити ECTS). 

Самостійна робота розподілена між двома взаємопов'язаними напрямами:
1. **Інженерний напрям (40 годин):** реалізація та розгортання наскрізного проєкту симуляції каскадної стійкості енергосистеми IEEE-118 (детальні вимоги — у [n01_power_grid_project.md](n01_power_grid_project.md)).
2. **Теоретично-сертифікаційний напрям (40 годин):** поглиблене опанування технологій за програмами міжнародних відкритих курсів, лабораторних треків вендорів та підготовка до фахової сертифікації.

---

## 1. Структура 80 годин самостійної роботи за темами курсу

Навчальна програма передбачає **10 тем для самостійного опрацювання (по 8 годин на кожну тему)**. Кожна тема інтегрує теоретичне опрацювання першоджерел, виконання інженерного завдання проєкту та проходження модулів рекомендованих курсів.

| № | Тема робочої програми (СРС) | Годин | Рекомендований онлайн-модуль / Сертифікаційний трек | Форма звітності та результат |
| :---: | :--- | :---: | :--- | :--- |
| **1** | **Тема 1.** Стохастичне моделювання Монте-Карло та топології великих графів (PowerGraph IEEE-118). | **8** | Coursera: *Cloud Computing Concepts, Part 1* (Univ. of Illinois) — Week 1–2 (MapReduce, Graph Processing). | Ініціалізація Git-репозиторію, верифікація середовища розробки, парсинг матриці інцидентності. |
| **2** | **Тема 2.** Порівняльний аналіз паралелізму в Linux: процеси (`fork`), нитки (`pthread`), пам'ять CoW, IPC канали. | **8** | edX / Linux Foundation: *Linux System Administration Basics* (LFS101x) / DeepLearning.AI: *Distributed Computing with Ray*. | Benchmark однопотокового vs багатопроцесорного (`multiprocessing.Pool`) виконання. Звіт про оверхед IPC. |
| **3** | **Тема 3.** Алгоритми планування в кластерах: Dominant Resource Fairness (DRF), Backfilling, Fair-Share (Slurm/PBS). | **8** | Ray Core Tutorials: *Ray Architecture & Core Internals* + Класична стаття NSDI: *DRF: Fair Allocation of Multiple Resource Types*. | Реалізація розрахунку DRF для двох типів ресурсів (CPU/Memory). Запуск розрахунку в Ray-кластері. |
| **4** | **Тема 4.** Механіка ізоляції ядра Linux: cgroups v2, Network Namespaces (veth), захист від вичерпання пам'яті (OOM). | **8** | Docker Training & Linux Foundation: *Introduction to Cloud Infrastructure Technologies* (LFS151x). | Профіль обмеження ресурсів: генерація витоку пам'яті у воркері, фіксація `Exit Code 137 OOMKilled`. |
| **5** | **Тема 5.** Multi-Tenancy та Noisy Neighbor: механізми Rate Limiting (Token Bucket, Leaky Bucket), ізоляція орендарів. | **8** | AWS Skill Builder: *Architecting Serverless Applications* / Coursera: *Cloud Computing Security*. | Реалізація фільтра запитів на базі Token Bucket у REST API / WebSocket шлюзі проєкту. |
| **6** | **Тема 6.** API Gateway та Service Mesh: Circuit Breaker, Exponential Backoff з Jitter, запобігання Retry Storm. | **8** | CNCF / edX: *Introduction to Service Mesh with Linkerd & Istio* (LFS144x). | Інтеграція Circuit Breaker для викликів розрахункового бекенду. Трасування аварійних повторів. |
| **7** | **Тема 7.** Розподілені сховища даних: об'єктні S3 API, шардинг, математика Consistent Hashing (Vnodes). | **8** | MIT 6.824 (Distributed Systems): *Lectures on Consistent Hashing and DHTs* (Chord/Dynamo). | Розрахунковий модуль: балансування ключів симуляції по 16 шардах, аналіз зміни дисперсії при $V_{nodes} = 100$. |
| **8** | **Тема 8.** Декларативна оркестрація Kubernetes: модель узгодження (Reconciliation), Raft в etcd, евристики `kube-scheduler`. | **8** | Linux Foundation / CNCF edX: *Introduction to Kubernetes* (LFS158x). | Маніфести `Job`, `Deployment`, `ConfigMap`. Розподіл подів за нодами з різними `requests`/`limits`. |
| **9** | **Тема 9.** Інструментування OpenTelemetry: розподілені трейси, контексти (W3C TraceContext), P90/P99 латентність. | **8** | OpenTelemetry Community Tutorials + Google SRE Book (*Monitoring Distributed Systems*). | Експорт спанів із клієнта та воркерів у Jaeger. Аналіз хвостової затримки P99 при навантаженні. |
| **10** | **Тема 10.** Хмарна економіка FinOps: моделі On-Demand vs Spot, Scale-to-Zero у FaaS, калькуляція TCO кластера. | **8** | FinOps Foundation: *FinOps Certified Practitioner (FOCP) Overview Track* / AWS Cloud Practitioner Essentials. | Інтерактивна таблиця FinOps: порівняльний розрахунок вартості 10 000 експериментів у AWS, GCP та On-Premise. |
| | **РАЗОМ** | **80** | | |

---

## 2. Рекомендовані міжнародні онлайн-курси та треки

Для виконання теоретичної та практичної частини самостійної роботи студентам пропонуються відкриті онлайн-курси від провідних університетів та професійних консорціумів.

### Трек A. Основи розподілених систем та хмарних концепцій
* **Cloud Computing Specialization** — *University of Illinois at Urbana-Champaign (Coursera)*
  - **Ключові теми:** Моделі хмарних обчислень, алгоритми узгодженості, консенсус Paxos/Raft, P2P та DHT-мережі, теорія CAP/PACELC.
  - **Корисність для курсу:** Складає теоретичний фундамент до Лекцій 0, 2, 6 та дає математичне обґрунтування алгоритмам планування й консистентного хешування.
  - **Посилання:** [Coursera: Cloud Computing Specialization](https://www.coursera.org/specializations/cloud-computing)

* **Distributed Computer Systems (MIT 6.824 / 6.5840)** — *MIT OpenCourseWare (Robert Morris)*
  - **Ключові теми:** Відмовостійкість, первинно-резервна реплікація, Raft-консенсус, лінеаризованість, архітектура Spanner та MapReduce.
  - **Корисність для курсу:** Еталонний інженерний курс для глибокого розуміння життєвого циклу розподілених станів та мережевих розділів (Network Partitions).
  - **Посилання:** [MIT 6.824 OpenCourseWare](https://pdos.csail.mit.edu/6.824/)

### Трек B. Контейнеризація, оркестрація та Cloud Native (CNCF)
* **LFS158x: Introduction to Kubernetes** — *The Linux Foundation & Cloud Native Computing Foundation (edX)*
  - **Ключові теми:** Архітектура Control Plane (`kube-apiserver`, `etcd`, `scheduler`), Pod lifecycle, абстракції Services, Ingress, Deployments, декларативне управління.
  - **Корисність для курсу:** Безпосередньо підтримує виконання Етапу 4 наскрізного проєкту (розгортання обчислювальних воркерів у Minikube/Kind).
  - **Посилання:** [edX: Introduction to Kubernetes (LFS158x)](https://www.edx.org/learn/kubernetes/the-linux-foundation-introduction-to-kubernetes)

* **LFS151x: Introduction to Cloud Infrastructure Technologies** — *The Linux Foundation (edX)*
  - **Ключові теми:** Механіка віртуалізації (KVM/QEMU), ядро Linux, Cgroups, Namespaces, шаруваті файлові системи Storage Drivers (OverlayFS).
  - **Корисність для курсу:** Поглиблює знання з Лекції 3 (ізоляція процесів та гіпервізори) та Етапу 3 наскрізного проєкту.
  - **Посилання:** [edX: Linux Foundation LFS151x](https://www.edx.org/learn/cloud-computing/the-linux-foundation-introduction-to-cloud-infrastructure-technologies)

### Трек C. Розподілені обчислення та Data/AI Infrastructure
* **Distributed Computing with Ray** — *Anyscale Academy / DeepLearning.AI*
  - **Ключові теми:** Асинхронні задачі (`@ray.remote`), актори зі станом (Stateful Actors), Ray Core, масштабування пакетних завдань без накладних витрат віртуалізації.
  - **Корисність для курсу:** Пряма інструкція до виконання Етапу 2 наскрізного проєкту (Ray-кластер без Docker) та практичного заняття 2.
  - **Посилання:** [Anyscale Academy: Ray Tutorials](https://docs.ray.io/en/latest/ray-core/walkthrough.html)

### Трек D. Інженерія надійності (SRE) та FinOps
* **Google Site Reliability Engineering (SRE) / Google Cloud Skills**
  - **Ключові теми:** Визначення SLI/SLO/SLA, бюджети помилок (Error Budgets), аналіз інцидентів, метрики хвостової латентності (Tail Latency P99), зниження рутини (Toil), Blameless Postmortems.
  - **Корисність для курсу:** Методологічна база для Лекції 8, 10 та лабораторного захисту відмовостійкості (Chaos Engineering з Jaeger).
  - **Посилання:** [Google Cloud Skills Boost: Developing a Google SRE Culture](https://www.cloudskillsboost.google/course_templates/148) та відкрита бібліотека [Google SRE Books](https://sre.google/books/)

* **AWS Cloud Practitioner Essentials / FinOps Fundamentals** — *AWS Training & FinOps Foundation*
  - **Ключові теми:** Моделі ціноутворення хмар (On-Demand, Savings Plans, Spot), структура датацентрів (AZ, Regions), калькуляція сукупної вартості володіння (TCO).
  - **Корисність для курсу:** Обов'язкова теоретична основа для підготовки фінального FinOps-розрахунку проєкту (пара 10).
  - **Посилання:** [AWS Skill Builder: Cloud Practitioner Essentials](https://explore.skillbuilder.aws/learn/course/external/view/elearning/134/aws-cloud-practitioner-essentials)

---

## 3. Визнання результатів неформальної освіти (Перезарахування)

Згідно з розділом 8 Робочої програми, здобувач може зарахувати проходження онлайн-матеріалів за простою формулою:

> **Формула зарахування:** **1 тема СРС = 1 завершений тижневий модуль курсу** (або практичний квест/бейдж). Загальний ліміт перезарахування за неформальну освіту — **до 20 балів максимум**.

1. **Що зараховується:**
   - Будь-який **один тиждень (Week/Module)** або окремий короткий курс із рекомендованих платформ (Coursera, edX, Linux Foundation, Google Cloud Skills, DeepLearning.AI тощо).
   - Не потрібно проходити всю спеціалізацію — достатньо закрити конкретний тематичний блок (наприклад, 1 модуль по MapReduce, 1 квест по Docker чи 1 лабу по Ray).
   - Наявність індустріального сертифіката (CKAD, AWS, GCP тощо) автоматично закриває максимум — **20 балів**.

2. **Як підтвердити:**
   - Посилання на цифровий сертифікат, публічний профіль (бейдж) або скріншот успішно складеного тесту/лабораторної з платформи.
   - Короткий коментар (3–5 хв на парі): як пройдений матеріал пов'язаний із вашим кодом у проєкті IEEE-118.

---

## 4. Рекомендована література для самостійного опрацювання

Під час виконання самостійної роботи обов'язковим є опрацювання ключових розділів академічних монографій:

1. **Martin Kleppmann. Designing Data-Intensive Applications.** O'Reilly Media, 2017.
   - *Розділи для СРС:* Глава 5 (Реплікація), Глава 6 (Шардинг та Consistent Hashing), Глава 8 (Проблеми розподілених систем: неправдиві годинники, спліт-брейн), Глава 9 (Узгодженість і консенсус).
2. **Brendan Burns. Designing Distributed Systems: Patterns and Paradigms for Scalable, Reliable Services.** O'Reilly Media, 2018.
   - *Розділи для СРС:* Розділ 1 (Sidecar Pattern), Розділ 2 (Ambassador), Розділ 4 (Replicated Load-Balanced Services), Розділ 6 (Event-Driven Processing).
3. **Beyer B. et al. Site Reliability Engineering: How Google Runs Production Systems.** O'Reilly Media, 2016. (Вільний доступ на [sre.google/books](https://sre.google/books/)).
   - *Розділи для СРС:* Глава 3 (Embracing Risk), Глава 4 (Service Level Objectives), Глава 25 (Data Processing Pipelines).
4. **Ghodsi A. et al. Dominant Resource Fairness: Fair Allocation of Multiple Resource Types.** In NSDI, 2011.
   - *Завдання СРС:* Аналіз властивостей Sharing Incentive, Strategy-proofness та Pareto-efficiency.
