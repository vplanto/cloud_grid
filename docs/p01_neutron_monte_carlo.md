# Практична робота 1: Симуляція Монте-Карло для ділення нейтронів з візуалізацією у браузері (MIMD на ПК)

> **Декларація курсу.** Академічна доброчесність та авторство матеріалів — у [DISCLAIMER.md](DISCLAIMER.md).

---

## 1. Мета роботи

Ознайомитися з практичною реалізацією паралельних обчислень за методом Монте-Карло на багатоядерних персональних комп'ютерах (архітектура **MIMD**). Навчитися розпаралелювати обчислювально місткі задачі за допомогою модуля `multiprocessing` у Python. Візуалізація траєкторій у браузері — **допоміжна** задача: простий веб-інтерфейс для перевірки результатів симуляції, а не головна мета роботи.

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

Файл — один модуль, який об'єднує **обчислювальне ядро**, **HTTP-сервер** і **headless-бенчмарк**. Нижче — карта файлу: у якому порядку йдуть блоки, які методи є і хто їх викликає. Без фрагментів коду — лише структура.

### 3.1. Блоки файлу (зверху вниз)

| № | Блок у `app.py` | Призначення |
| :--- | :--- | :--- |
| 1 | `import …` | Стандартна бібліотека: `argparse`, `json`, `multiprocessing`, `HTTPServer` |
| 2 | `class ReactorSimulationEngine` | Стан реактора та один тик симуляції (`step`) |
| 3 | `def update_neutrons_chunk` | Обчислення Монте-Карло для одного шматка масиву нейтронів (воркер) |
| 4 | `engine = ReactorSimulationEngine()` | Глобальний екземпляр двигуна — спільний для веб-режиму |
| 5 | `HTML_PAGE = """…"""` | Вбудована HTML-сторінка з CSS, Canvas і JavaScript (dashboard) |
| 6 | `class ReactorHandler` | HTTP-обробник: `GET /` і `POST /api/*` |
| 7 | `def run_headless_benchmark` | Консольний прогін без браузера + запис JSON |
| 8 | `def main` | Точка розгалуження: веб-сервер або `--headless` |
| 9 | `if __name__ == "__main__"` | Запуск `main()` при прямому виклику скрипта |

### 3.2. Методи Python і місця виклику

#### `ReactorSimulationEngine`

| Метод | Що робить | Хто викликає |
| :--- | :--- | :--- |
| `__init__()` | Створює двигун із дефолтними параметрами (паливо 50%, 350k fast + 150k slow, `num_workers = cpu_count()`) | `engine = ReactorSimulationEngine()` при завантаженні модуля |
| `reset_params(params)` | Скидає лічильники, перегенеровує початковий масив `self.neutrons` за `fuel_mass`, `n_fast`, `n_slow`, `num_workers` | `__init__()`; `ReactorHandler.do_POST()` → `POST /api/reset`; `run_headless_benchmark()` на старті бенчмарку |
| `get_state()` | Повертає знімок стану **без** обчислення тику (статус, k, вибірка до 750 нейтронів для Canvas) | `step()` — якщо активних нейтронів 0 або > 3.5M (ранній вихід) |
| `step()` | Один тик: шардить `self.neutrons`, запускає `Pool.map(update_neutrons_chunk, …)`, зливає результати, рахує `k_factor` і `status` | `ReactorHandler.do_POST()` → `POST /api/step`; цикл у `run_headless_benchmark()` |

#### `update_neutrons_chunk` (функція модуля, не метод класу)

| Функція | Що робить | Хто викликає |
| :--- | :--- | :--- |
| `update_neutrons_chunk(args)` | Для кожного нейтрона в chunk: рух → виліт / ділення / поглинання / розсіювання. Повертає `{survived, fissions, absorbed, escaped, new_born}` | `ReactorSimulationEngine.step()` через `multiprocessing.Pool.map(...)` — по одному виклику на кожен CPU-воркер і chunk |

#### `ReactorHandler` (HTTP)

| Метод | Що робить | Хто викликає |
| :--- | :--- | :--- |
| `do_GET()` | `GET /` або `/index.html` → віддає `HTML_PAGE` | Браузер при відкритті `http://localhost:8080/` |
| `do_POST()` | Маршрутизація: `/api/reset` → `engine.reset_params()`; `/api/step` → `engine.step()` → JSON у відповідь | JavaScript у `HTML_PAGE`: `fetch('/api/reset')` з `applyParams()`, `fetch('/api/step')` з `stepSimulation()` |

#### Точка входу та бенчмарк

| Функція | Що робить | Хто викликає |
| :--- | :--- | :--- |
| `run_headless_benchmark(params, max_steps, output_file)` | `reset_params` → цикл `step()` до `max_steps` або термінального статусу → друк метрик → `benchmark_results_mimd_pc.json` | `main()` при прапорці `--headless` |
| `main()` | Розбирає CLI (`--headless`, `--fuel`, `--fast`, `--slow`, `--steps`, `--workers`, `--port`, `--out`); або бенчмарк, або `HTTPServer.serve_forever()` | `if __name__ == "__main__"` |

### 3.3. JavaScript у `HTML_PAGE` (клієнтська частина)

Вбудований у рядок `HTML_PAGE`, не окремий файл:

| Функція | Що робить | Хто викликає |
| :--- | :--- | :--- |
| `drawReactorCore()` | Малює коло активної зони на Canvas | Завантаження сторінки; після кожного `stepSimulation()` і `applyParams()` |
| `stepSimulation()` | `POST /api/step` → оновлює метрики й точки нейтронів на Canvas | `toggleRun()` (кожні 250 ms); `applyParams()` після reset |
| `toggleRun()` | Старт/пауза `setInterval(stepSimulation, 250)` | Кнопка «Запустити неперервно» |
| `applyParams(params)` | `POST /api/reset` з JSON-параметрами → один крок симуляції | `loadPreset('explosion' \| 'control' \| 'extinction')` |
| `loadPreset(name)` | Виставляє слайдери пресету й викликає `applyParams()` | Кнопки 💥 / 🔋 / ❄️ на dashboard |

### 3.4. Граф викликів (два режими запуску)

```mermaid
flowchart TD
    subgraph Entry ["Точка входу"]
        CLI["python3 app.py"] --> Main["main()"]
        Main -->|"--headless"| Bench["run_headless_benchmark()"]
        Main -->|"за замовчуванням"| HTTP["HTTPServer + ReactorHandler"]
    end

    subgraph Headless ["Headless-режим"]
        Bench --> RP1["engine.reset_params()"]
        RP1 --> Loop["цикл step()"]
        Loop --> StepH["engine.step()"]
        StepH --> MapH["Pool.map(update_neutrons_chunk)"]
        Loop --> JSON["запис benchmark_results_*.json"]
    end

    subgraph Web ["Веб-режим"]
        HTTP --> GET["do_GET() → HTML_PAGE"]
        HTTP --> POST["do_POST()"]
        POST -->|"POST /api/reset"| RP2["engine.reset_params()"]
        POST -->|"POST /api/step"| StepW["engine.step()"]
        StepW --> MapW["Pool.map(update_neutrons_chunk)"]
        GET --> Browser["браузер: loadPreset → applyParams → stepSimulation"]
        Browser --> POST
    end
```

### 3.5. Обчислювальне ядро та MIMD-шар

Нижче — деталізація саме обчислювального контуру (те, що відбувається всередині `step()` → `update_neutrons_chunk`).

#### Схема алгоритму `update_neutrons_chunk`

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

2. **Паралельний пул (`multiprocessing.Pool`):** Усередині `ReactorSimulationEngine.step()` — шардинг масиву та `pool.map(update_neutrons_chunk, task_args)`.

#### Схема паралельного розподілу в `step()`

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

3. **Веб-шар (`ReactorHandler` + `HTML_PAGE`):** `do_GET` віддає dashboard; `do_POST` на `/api/reset` і `/api/step` делегує в `engine`. Клієнтська частина (Rendering Path, `POST`) — [Лекція 4: Браузер зсередини](https://vplanto.github.io/java_script/04_browser_internals.html), [Лекція 7: HTTP/S та REST](https://vplanto.github.io/java_script/07_http_rest.html).

```
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                           Веб-браузер (Клієнт)                              │
 │     loadPreset / toggleRun → stepSimulation / applyParams → Canvas          │
 └──────────────────────────────────────┬──────────────────────────────────────┘
                                        │ POST /api/step  ·  POST /api/reset
                                        ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │              ReactorHandler (Main Process) → engine.step() / reset_params() │
 └──────────────────────────────────────┬──────────────────────────────────────┘
                                        │ multiprocessing.Pool.map
                ┌───────────────────────┼───────────────────────┐
                ▼                       ▼                       ▼
     ┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐
     │ update_neutrons_chunk│ │ update_neutrons_chunk│ │ update_neutrons_chunk│
     │   (Worker / Core 1)  │ │   (Worker / Core 2)  │ │   (Worker / Core N)  │
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
