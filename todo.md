# Внутрішні нотатки (не для студентів)

Агностичний чеклист: що не забути при доопрацюванні курсу. З інших документів сюди **не посилаємось**.

---

## Консенсус, CAP і etcd

**Контекст (як у сильних DS-курсах):** консенсус (Raft/Paxos), CAP-теорема, split-brain — ядро розподілених систем. У MIT 6.5840 на Raft йде суттєва частина семестру.

**Як у нас:** консенсус повністю винесено в блокчейн-курс (окремий етап 5 там). Cloud/Grid це не дублює.

**Ризик:** магістр, який пройшов Cloud/Grid, але не чув про quorum consensus, vector clocks і CAP, не розуміє:
- навіщо **etcd** у Kubernetes як єдине джерело правди;
- чому NoSQL/розподілені сховища поводяться інакше при **розділенні мережі** (partition).

**Що зробити (мінімум):**
- Не змушувати писати Raft руками.
- У **лекцію 6** (розподілене зберігання) додати **~20 хв** концептуального блоку:
  - CAP (consistency / availability / partition tolerance) — інтуїція, не доказ;
  - quorum read/write — чому «більшість вузлів» = рішення;
  - etcd у K8s: control plane, reconciliation loop, зв'язок з лекцією 7.
- За бажанням: 1 слайд «vector clocks — навіщо порядок подій у мережі без глобального годинника» (без лабораторної).

**Не забути:** згадати split-brain як наслідок partition без quorum; не плутати з Noisy Neighbor (інший шар).

---

## Object Storage і черги подій — теорія vs код

**Контекст (Stanford CS349D, ETH):** якщо на лекції S3 / message queues — студент хоча б раз торкається в коді.

**Як у нас:** усі 5 захистів крутяться навколо симулятора IEEE-118. Каскади й benchmark — сильні; **MinIO/S3**, **consistent hashing** у реалізації, **Kafka/RabbitMQ** лишаються на слайдах (лекції 5–6, 9).

**Ризик:** «чув на лекції — не робив» для storage і event-driven шару.

**Бажано (навряд чи встигнемо в поточному семестрі):**
- На **КТ 2 або КТ 3** (етапи 3–4): воркери після batch trials віддають агрегат не лише в локальний `JSON`, а:
  - **Object Storage** (MinIO, S3-сумісний API) — immutable append результатів; або
  - **Redis / черга** (RabbitMQ, Kafka) — асинхронна передача між API і compute-воркером.
- Це зв'язує лекції 5–6 з docker-compose / K8s без нового «паралельного» проєкту.

**Якщо не встигнемо:**
- лишити в лекціях явний callout: «у проєкті зараз file-based; у проді — object store / queue»;
- демо MinIO/redis одним `docker-compose` на майстер-класі викладача (без зміни критеріїв здачі).

---

## Landmark papers (першоджерела)

**Контекст (MIT 6.5840, Stanford CS349D тощо):** перед лекцією магістри читають **1 канонічну статтю** — Borg, Dynamo, MapReduce, Ray (OSDI) тощо. Інструмент сприймається як **інженерний винахід з trade-off**, а не як «готовий магазинний продукт».

**Як у нас:** студенти читають лише конспект курсу. K8s, S3, Kafka виглядають як чорна скринька без історії рішень.

**Ризик:** на захисті не можуть пояснити *чому* Dynamo відмовилася від ACID або чому Borg передував Kubernetes.

**Що зробити:**
- До **кожної лекції 0–10** у силабусі (`index.md` або шапка файлу лекції) — блок **Reading**:
  - **1 обов'язкова** або **рекомендована** стаття (PDF / DOI / USENIX);
  - 2–3 речення: *що саме читати* (розділ, не весь tom);
  - 1 питання для обговорення на парі («який trade-off автори зробили?»).
- Не вимагати рефератів — достатньо усного «що запам'ятали» на початку лекції (5 хв).
- Публічно в курс **не** посилатись на `todo.md`; список статей — у силабусі або в кінці кожної лекції.

**Чернетка відповідності (перевірити посилання перед семестром):**

| Лекція | Тема (коротко) | Кандидат на reading | Примітка |
| :---: | :--- | :--- | :--- |
| **0** | MC, еволюція обчислень | Metropolis et al., *The Monte Carlo Method* (1953) або огляд von Neumann architecture | зв'язок з лекцією 0 |
| **1** | Flynn, залізо | Flynn, *Very High-Speed Computing Systems* (1966) | первинне джерело таксономії |
| **2** | Batch vs Cloud, schedulers | Ghodsi et al., *Dominant Resource Fairness* (2011); опц.: Verma et al., *Large-scale cluster management at Google with Borg* (або витяг про scheduling) | DRF ↔ Slurm-логіка; Borg — місток до лек. 7 |
| **3** | VM vs containers | Barham et al., *Xen and the Art of Virtualization* (SOSP 2003); опц.: Merkel, *Docker: lightweight Linux containers* | Type-1/2, namespaces — у supplementary |
| **4** | Multi-tenant, Noisy Neighbor | Hamilton, *On Designing and Deploying Internet-Scale Services* (2007) або AWS Well-Architected excerpt | tenancy, blast radius |
| **5** | CNI, mesh, API GW | Burns et al., *Design Patterns for Container-Based Distributed Systems* (2016); опц.: Phipps et al., *Istio* / Envoy intro | sidecar pattern |
| **6** | Storage, CAP, hashing | DeCandia et al., *Dynamo: Amazon's Highly Available Key-value Store* (2007); Karger et al., *Consistent Hashing* (1997) | **+ CAP-блок** з розділу вище |
| **7** | K8s, control plane | Burns et al., *Borg, Omega, and Kubernetes* (2016) або Verma et al., *Borg* (2015) | etcd — після Dynamo/Borg |
| **8** | Observability | Sigelman et al., *Dapper, a Large-Scale Distributed Systems Tracing Infrastructure* (2010) | spans, sampling |
| **9** | Events, FaaS | Kreps et al., *Kafka: a Distributed Messaging System* (2011); опц.: Jonas et al., *Cloud Programming Simplified* (Berkeley serverless view) | delivery guarantees |
| **10** | FinOps, Chaos | Basiri et al., *Chaos Engineering* (Netflix, 2016); опц.: Hindman et al., *Mesos* (resource offers) для TCO контексту | синтез курсу на захисті |

**Не забути:**
- [ ] Для кожної статті — перевірити, що PDF відкритий студентам (campus VPN / DOI).
- [ ] Українськомовний конспект лишається основним; paper — **додаток**, не заміна лекції.
- [ ] Уникати 10 важких paper на тиждень: позначати **обов'язково** vs **додатково** (★).
- [ ] Лекція 6: узгодити Dynamo/CAP з блокчейн-курсом (не тричі той самий Raft).

---

## Швидкий огляд прогалин

| Тема | Де зараз | Мінімум | Бажано (опційно) |
| :--- | :--- | :--- | :--- |
| CAP, quorum, etcd | Блокчейн-курс | ~20 хв у лекції 6 | — |
| Vector clocks | — | 1 слайд у лекції 6 | — |
| S3 / MinIO | Лекція 6 | callout у лекції | запис результатів trials на КТ 2–3 |
| Consistent hashing | Лекція 6 | лишається теорія + діаграма | shard key у metadata object store |
| Kafka / RabbitMQ | Лекція 9 | callout + демо викладача | черга між API і MC-воркером |
| Landmark papers | — | Reading-блок у 11 лекціях | 1 paper / лекція в силабусі |

---

## Інше (додавати по ходу)

- [ ] Перед записом лекції 6 — перевірити, що CAP-блок не дублює блокчейн-курс дослівно; узгодити термінологію з колегою.
- [ ] Якщо MinIO на лабах — один compose-файл-референс у `source/`, не вимога до всіх студентів.
- [ ] Оновити критерії КТ лише після пілоту на одній групі; не змінювати правила серед семестру без оголошення.
- [ ] Заповнити Reading у шапках лекцій 3–10 за чернеткою таблиці вище; лекції 0–2 — при наступному редагуванні.
