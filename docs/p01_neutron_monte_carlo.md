# Практична робота 1: Симуляція Монте-Карло для ділення нейтронів з візуалізацією у браузері (MIMD на ПК)

> **Декларація курсу.** Академічна доброчесність та авторство матеріалів — у [DISCLAIMER.md](DISCLAIMER.md).

---

## 1. Мета роботи

Ознайомитися з практичною реалізацією паралельних обчислень за методом Монте-Карло на багатоядерних персональних комп'ютерах (архітектура **MIMD**). Навчитися розпаралелювати обчислювально місткі задачі за допомогою модуля `multiprocessing` у Python та будувати веб-інтерфейс для візуалізації траєкторій у браузері.

---

## 2. Постановка задачі

Повна математична та фізична постановка задачі переносу та ділення нейтронів методом Монте-Карло доступна у документі **[Постановка задачі (source/README.md)](https://github.com/vplanto/cloud_grid/blob/main/source/README.md)**.

### 2.1. Ймовірнісний граф станів нейтрона
Схема ймовірностей для кожного кроку переносу нейтронів:

```mermaid
graph LR
    T["Traveling<br>(Рух / Вільний пробіг)"]
    LA["Leave or Absorb<br>(Виліт або Поглинання)"]
    F["Fission<br>(Ділення ядра)"]

    T -->|"0.42 (Scatter / Розсіювання)"| T
    T -->|"0.20"| LA
    T -->|"0.38"| F

    style T fill:#064e3b,color:#fff,stroke:#34d399,stroke-width:2px
    style LA fill:#4c1d95,color:#fff,stroke:#a78bfa,stroke-width:2px
    style F fill:#7f1d1d,color:#fff,stroke:#f87171,stroke-width:2px
```

### 2.2. Дерево каскадної ланцюгової реакції та коефіцієнт розмноження ($k$)
Дерево розгалуження генерацій нейтронів при діленні ядер:

```mermaid
graph LR
    subgraph Gen0 ["Генерація 0"]
        T0["Traveling"]
        T0 -->|"0.40 (Scatter)"| T0
        T0 -->|"0.20"| LA0["Leave or absorb"]
        T0 -->|"0.40"| F0["Fission"]
    end

    subgraph Gen1 ["Генерація 1"]
        F0 --> T1_1["Traveling"]
        F0 --> T1_2["Traveling"]

        T1_1 --> T1_1
        T1_1 --> LA1_1["Leave or absorb"]
        T1_1 --> F1_1["Fission"]

        T1_2 --> T1_2
        T1_2 --> LA1_2["Leave or absorb"]
        T1_2 --> F1_2["Fission"]
    end

    subgraph Gen2 ["Генерація 2"]
        F1_2 --> N3_1["Traveling"]
        F1_2 --> N3_2["Traveling"]
        F1_2 --> N3_3["Traveling"]
    end

    style T0 fill:#1e293b,color:#fff,stroke:#38bdf8,stroke-width:2px
    style F0 fill:#7f1d1d,color:#fff,stroke:#f87171,stroke-width:2px
    style F1_1 fill:#7f1d1d,color:#fff,stroke:#f87171,stroke-width:2px
    style F1_2 fill:#7f1d1d,color:#fff,stroke:#f87171,stroke-width:2px
```

---

## 3. Вихідний код та архітектура MIMD

Готовий реалізований Python-проєкт розміщено в каталозі [`source/mimd-pc/app.py`](https://github.com/vplanto/cloud_grid/blob/main/source/mimd-pc/app.py).

### Архітектура системи:
1. **Обчислювальне ядро (`update_neutrons_chunk`):** Виконується в окремих воркер-процесах і симулює перенос та взаємодію масиву нейтронів на кожному тику.

#### Схема алгоритму обчислювального ядра (`update_neutrons_chunk`):

```mermaid
flowchart TD
    Start["Вхідний масив нейтронів (Chunk)"] --> Loop["Для кожного нейтрона (i = 1..N)"]
    Loop --> Move["1. Оновлення координат:<br>nx = x + vx, ny = y + vy"]
    Move --> EscapeCheck{"2. Виліт за межі зони?<br>sqrt(nx² + ny²) ≥ R"}
    
    EscapeCheck -->|"Так"| Escaped["Виліт з реактора<br>(escaped + 1)"]
    EscapeCheck -->|"Ні (у зоні)"| EventRoll

    subgraph MC_Block ["🎲 СИМУЛЯЦІЯ МОНТЕ-КАРЛО (Взаємодія)"]
        direction TB
        EventRoll{"3. Розіграш події<br>(r ~ Uniform)"}
        
        EventRoll -->|"r < σ_f"| Fission["Ділення ядра:<br>fissions + 1,<br>+2..3 нейтрони"]
        EventRoll -->|"σ_f ≤ r < σ_f + σ_a"| Absorb["Поглинання:<br>absorbed + 1"]
        EventRoll -->|"σ_f + σ_a ≤ r < σ_t"| Scatter["Розсіювання:<br>зміна кута θ"]
        EventRoll -->|"r ≥ σ_t"| FreeTravel["Вільний пробіг:<br>без взаємодії"]
    end

    Fission --> Collect["Збір виживших нейтронів"]
    Scatter --> Collect
    FreeTravel --> Collect

    Collect --> Next["Перехід до наступного нейтрона"]
    Absorb --> Next
    Escaped --> Next

    Next -.->|"Наступна ітерація"| Loop
    Loop -->|"Усі нейтрони оброблено"| End["Результат воркера:<br>{survived, fissions, absorbed, escaped}"]

    style MC_Block fill:#0f172a,color:#38bdf8,stroke:#0284c7,stroke-width:2px,stroke-dasharray: 4 4
    style Start fill:#1e293b,color:#fff,stroke:#38bdf8,stroke-width:2px
    style Move fill:#1e293b,color:#fff,stroke:#64748b,stroke-width:1px
    style EscapeCheck fill:#451a03,color:#fff,stroke:#f97316,stroke-width:2px
    style EventRoll fill:#7c2d12,color:#fff,stroke:#ea580c,stroke-width:2px
    style Fission fill:#7f1d1d,color:#fff,stroke:#f87171,stroke-width:2px
    style Absorb fill:#4c1d95,color:#fff,stroke:#a78bfa,stroke-width:2px
    style Scatter fill:#064e3b,color:#fff,stroke:#34d399,stroke-width:2px
    style FreeTravel fill:#1e1b4b,color:#fff,stroke:#818cf8,stroke-width:2px
    style Escaped fill:#312e81,color:#fff,stroke:#818cf8,stroke-width:1px
    style Collect fill:#0f766e,color:#fff,stroke:#14b8a6,stroke-width:2px
    style Next fill:#334155,color:#fff,stroke:#94a3b8,stroke-width:1px
    style End fill:#0284c7,color:#fff,stroke:#38bdf8,stroke-width:2px
```

2. **Паралельний пул (`multiprocessing.Pool`):** Розподіляє масив початкових нейтронів між ядрами CPU (MIMD-обчислення).

#### Схема паралельного розподілу задач MIMD (`multiprocessing.Pool`):

```mermaid
flowchart TD
    MainProc["Головний процес (Main Process)"] --> InputBatch["Масив активних нейтронів N"]
    InputBatch --> Splitter["Шардинг масиву (Array Chunking):<br>chunk_size = N / num_workers"]
    
    Splitter --> Chunk0["Chunk 0<br>(Нейтрони 1..C)"]
    Splitter --> Chunk1["Chunk 1<br>(Нейтрони C+1..2C)"]
    Splitter --> ChunkN["Chunk N-1<br>(Нейтрони ...)"]

    subgraph MIMD_MC ["🎲 ПАРАЛЕЛЬНЕ ОБЧИСЛЕННЯ МЕТОДУ МОНТЕ-КАРЛО (MIMD CPU CORES)"]
        Chunk0 --> Worker0["Worker 0 (CPU Core 1)<br>update_neutrons_chunk()"]
        Chunk1 --> Worker1["Worker 1 (CPU Core 2)<br>update_neutrons_chunk()"]
        ChunkN --> WorkerN["Worker N (CPU Core N)<br>update_neutrons_chunk()"]
    end

    Worker0 --> Res0["Результат 0:<br>{survived, fissions, ...}"]
    Worker1 --> Res1["Результат 1:<br>{survived, fissions, ...}"]
    WorkerN --> ResN["Результат N-1:<br>{survived, fissions, ...}"]

    Res0 --> Reduce["Агрегація результатів (Reduce/Merge):<br>next_neutrons = sum(survived)<br>total_fissions += sum(fissions)"]
    Res1 --> Reduce
    ResN --> Reduce

    Reduce --> StateUpdate["Оновлення глобального стану реактора<br>Розрахунок k_eff та підсумкового статусу"]

    style MIMD_MC fill:#0f172a,color:#38bdf8,stroke:#0284c7,stroke-width:3px,stroke-dasharray: 5 5
    style MainProc fill:#1e293b,color:#fff,stroke:#38bdf8,stroke-width:2px
    style Worker0 fill:#064e3b,color:#fff,stroke:#34d399,stroke-width:2px
    style Worker1 fill:#064e3b,color:#fff,stroke:#34d399,stroke-width:2px
    style WorkerN fill:#064e3b,color:#fff,stroke:#34d399,stroke-width:2px
    style StateUpdate fill:#0284c7,color:#fff,stroke:#38bdf8,stroke-width:2px
```

3. **Вбудований веб-сервер та Dashboard (`HTTPServer`):** Приймає параметри з браузера, запускає симуляцію та повертає JSON із траєкторіями для візуалізації на 2D Canvas. Клієнтська частина (Rendering Path, `POST`) — [Лекція 4: Браузер зсередини](https://vplanto.github.io/java_script/04_browser_internals.html), [Лекція 7: HTTP/S та REST](https://vplanto.github.io/java_script/07_http_rest.html).

```
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                           Веб-браузер (Клієнт)                              │
 │            Інтерактивна Canvas-візуалізація + HTML Dashboard                │
 └──────────────────────────────────────┬──────────────────────────────────────┘
                                        │ HTTP POST /api/simulate (JSON)
                                        ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                     Python HTTP Server (Main Process)                       │
 └──────────────────────────────────────┬──────────────────────────────────────┘
                                        │ multiprocessing.Pool (MIMD)
                ┌───────────────────────┼───────────────────────┐
                ▼                       ▼                       ▼
     ┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐
     │ Worker 1 (CPU Core) │ │ Worker 2 (CPU Core) │ │ Worker N (CPU Core) │
     └─────────────────────┘ └─────────────────────┘ └─────────────────────┘
```

---

## 4. Інструкція із запуску та інтерфейс

### Крок 1. Запуск неперервного серверного застосунку
Відкрийте термінал у корені проєкту та виконайте команду:

```bash
python3 source/mimd-pc/app.py
```

Ви побачите повідомлення:
```text
=== Monte Carlo Reactor Simulation (MIMD PC) ===
Server running at http://localhost:8080/
CPU Cores Available: 8
```

### Крок 2. Робота у браузері та Швидкі Демо-Пресет Режими
Перейдіть за адресою [http://localhost:8080/](http://localhost:8080/) у браузері.

Для миттєвої демонстрації у верхній частині панелі доступні **3 кнопки Демо-Пресетів (Мега-масштаб 1M+)**:
- 💥 **[Вибух]:** 90% палива, 600,000 швидких та 300,000 повільних нейтронів → неконтрольоване розмноження до 1,500,000+ частинок.
- 🔋 **[Контроль]:** 50% палива, 350,000 швидких та 150,000 повільних нейтронів → утримує рівноважний критичний стан ($k \approx 1.0$).
- ❄️ **[Затухання]:** 25% палива, 150,000 швидких та 30,000 повільних нейтронів → згасання реакції ($k < 0.75$).

Паралельний розрахунок **500,000 – 1,500,000 активних нейтронів** на пулі процесів `multiprocessing.Pool` завантажує 100% усіх ядер процесора в `htop` на кожному тику симуляції.

### Крок 3. Запуск у Headless Бенчмарк-режимі (Без браузера)
Для точного вимірювання продуктивності CPU, фіксації часу виконання та подальшого порівняння з іншими архітектурами (GPU, Cloud кластери) розроблено консольний Headless-режим:

```bash
python3 source/mimd-pc/app.py --headless --steps 30 --out source/mimd-pc/benchmark_results_mimd_pc.json
```

Параметри консольного запуску:
- `--headless`: Запуск без підйому веб-сервера (чисті CLI-обчислення);
- `--steps 30`: Кількість тиків симуляції для бенчмарку;
- `--fuel 50`: Кількість палива в реакторі (%);
- `--fast 350000` / `--slow 150000`: Початковий масив частинок;
- `--out source/mimd-pc/benchmark_results_mimd_pc.json`: Збереження підсумкового JSON-звіту для подальшого порівняння.

---

## 5. Завдання для практичного виконання

### Завдання 1. Дослідження демо-режимів реактора (Мега-Масштаб 1M+)
1. Почергово натисніть кнопки пресетів **💥 Вибух**, **🔋 Контроль**, **❄️ Затухання**.
2. Зафіксуйте кількість активних нейтронів, кількість подій ділення ядра та підсумковий коефіцієнт $k$.
3. Заповніть порівняльну таблицю:

| Демо-Режим | Паливо (%) | Швидкі | Повільні | Підсумковий статус | Коефіцієнт $k$ |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Вибух** | 90% | 600 000 | 300 000 | 💥 EXPLOSION | $> 1.10$ |
| **Контроль** | 50% | 350 000 | 150 000 | 🔋 STABLE_RUN | $\approx 1.00$ |
| **Затухання** | 25% | 150 000 | 30 000 | ❄️ EXTINCTION | $< 0.75$ |

### Завдання 2. Headless-бенчмарк та фіксація результатів для порівняння
1. Запустіть Headless-бенчмарк на 30 кроків:
   `python3 source/mimd-pc/app.py --headless --steps 30`
2. Перевірте згенерований файл [`source/mimd-pc/benchmark_results_mimd_pc.json`](https://github.com/vplanto/cloud_grid/blob/main/source/mimd-pc/benchmark_results_mimd_pc.json).
3. Занотуйте підсумкові метрики для майбутнього порівняльного аналізу з GPU/Cloud архітектурами:
   - Загальний час виконання $T_{\text{total}}$ (сек);
   - Середній час обчислення одного тику $T_{\text{step}}$ (мс);
   - Швидкість прорахунку частинок (нейтронів/сек).

---

## 6. Контрольні питання

<details markdown="1">
<summary><b>1. Чому симуляцію переносу нейтронів методом Монте-Карло називають "ідеально паралельною" (Embarrassingly Parallel) задачею?</b></summary>

Тому що доля кожного початкового нейтрона обчислюється повністю автономно та незалежно від інших нейтронів. Вузлам (Worker процесам) не потрібно синхронізувати стан або обмінюватися даними в процесі симуляції, що зводить накладні витрати на міжпроцесну взаємодію до мінімуму.
</details>

<details markdown="1">
<summary><b>2. Що відбувається з прискоренням (Speedup), якщо задати кількість воркерів `num_workers` більшою за кількість фізичних або віртуальних ядер процесора?</b></summary>

Прискорення перестає рости — і починає падати. Зайвий воркер = context switching, боротьба за кеш. Фізичних ядер більше не стає.
</details>

<details markdown="1">
<summary><b>3. Як зміна перерізу розсіювання $\Sigma_s$ впливає на коефіцієнт критичності $k_{eff}$ при незмінному радіусі $R$?</b></summary>

Збільшення $\Sigma_s$ зростає ймовірність відскоку нейтрона всередині зони. Це подовжує траєкторію нейтрона всередині реактора, зменшує ймовірність його вильоту назовні (Escaped) та збільшує ймовірність ділення ядра, що підвищує $k_{eff}$.
</details>
