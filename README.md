# Quarto

## اجرای بازی محلی

Python 3 لازم است؛ سرویس و تست‌ها فقط از کتابخانهٔ استاندارد Python استفاده می‌کنند.
از پوشهٔ پروژه اجرا کنید:

```powershell
python -B .\quarto_web.py --port 8000
```

سپس در مرورگر به `http://127.0.0.1:8000/` بروید. سرویس فقط روی loopback گوش می‌دهد.
برای انتخاب پورت دیگر، مقدار `--port` را عوض کنید؛ برای نمونه `--port 8123`.
برای توقف سرویس در همان پنجرهٔ ترمینال، `Ctrl+C` را فشار دهید.

صفحه با refresh بازی را از state حافظه‌ای سرویس دوباره می‌خواند و بازی ادامه پیدا می‌کند.
توقف و راه‌اندازی دوبارهٔ سرویس state را پاک می‌کند و بازی تازه لازم خواهد بود.
این نمونه یک بازی مشترک در حافظه دارد؛ چند پنجرهٔ مرورگر به همان بازی متصل می‌شوند.

## اجرای تست‌ها

```powershell
python -B -m unittest discover -s tests -v
```

فرمان بالا تست‌های موتور، runner و API محلی را اجرا می‌کند و به اینترنت نیاز ندارد.
گزینهٔ `-B` از تولید فایل‌های bytecode پایتون جلوگیری می‌کند.

## API محلی

- `GET /api/state` — state فعلی و actionهای مجاز موتور.
- `GET /api/pieces` — ۱۶ مهره با ویژگی‌هایی که مستقیماً از موتور می‌آیند.
- `POST /api/games` — شروع بازی با JSON مانند `{"mode":"classic"}` یا
  `{"mode":"self_selection"}`.
- `POST /api/actions` — ارسال action شامل `kind`، `player` و فیلدهای مربوط به action.

موتور Python مرجع اعتبار action، نوبت و نتیجه است. فایل‌های قدیمی رابط در پروژه حفظ شده‌اند،
اما صفحهٔ اصلی از منطق JavaScript قدیمی استفاده نمی‌کند. فایل‌های UI از فهرست مجاز مشخص
سرو می‌شوند؛ فایل‌های Python، تنظیمات Git، تست‌ها و آرشیوها از HTTP ارائه نمی‌شوند.

Replayها و قابلیت‌های agent در رابط مرورگر این مرحله را شامل نمی‌شوند. این پروژه نیز ادعای
سازگاری رسمی با Kaggle ندارد.

## وضعیت فعلی و محدودیت‌ها

این رابط یک نمونهٔ اولیهٔ محلی است و بازطراحی بصری آن در این مرحله انجام نشده است.
در بررسی دستی، جریان بازی و عملکرد موتور درست به نظر رسیدند؛ این مشاهده اثبات کامل‌بودن
موتور یا رابط کاربری نیست.

مسیر اصلی تعامل، کلیک روی مهره برای انتخاب و سپس کلیک روی خانهٔ خالی برای قراردادن آن است.
Drag-and-drop نیز کار می‌کند، اما هنوز ایرادهای ظاهری و عملکردی دارد. محل و تراز قرارگیری
مهره‌ها هم نیازمند اصلاح است؛ به این ترتیب، drag-and-drop فعلاً مسیر پیشنهادی برای بازی نیست.

## Local hidden-information benchmark experiment

The local experiment is in
[`notebooks/quarto_hidden_information_v1.ipynb`](./notebooks/quarto_hidden_information_v1.ipynb).
It uses the reusable implementation in `hidden_quarto_benchmark.py` and the frozen
PubChem snapshot in `data/`; it has no Kaggle integration or new package dependencies.
Run its regression suite from the project root with:

```powershell
python -B -m unittest discover -s tests -v
```

The current default public seed is `1729`. Its deterministic 16-element sample has
zero valid four-attribute quartets, so the benchmark correctly refuses to start the
draft or Quarto game. The notebook reports this feasibility result rather than
changing the seed, properties, or source values. This is a scientific/data blocker,
not a passing end-to-end hidden-information game.

## FMA Quarto pilot

The approved seed-11 FMA candidate is persisted in `fma_pilot_instance.json` and
reloaded by `fma_pilot.py` without selecting a replacement quartet. The local
two-seat regression uses deterministic fake agents; it is a plumbing check, not a
model benchmark:

```powershell
python -B -m unittest discover -s tests -p "test_fma_pilot.py" -v
```

The FMA archive is deliberately not copied into the Kaggle source snapshot. Before
running the Task, mount the archive at a permitted input path, set
`QUARTO_FMA_ARCHIVE_PATH` to that path, and set `QUARTO_FMA_LICENSE_APPROVED=1`
only after confirming that the applicable license permits the intended use. The
Task verifies the pinned archive hash and the fixed candidate, then runs the real
adapter and security preflight. It fails closed if either runtime input is absent.

The source snapshot includes an `ATTRIBUTION.md` notice; the repository copy is
[`FMA_ATTRIBUTION.md`](./FMA_ATTRIBUTION.md). It credits the FMA authors and
describes the four selected `features.csv` columns, fixed threshold binarization,
and approved 16-row instance. The license audit is **CONDITIONALLY CONFIRMED**,
not legal approval: coverage of audio-derived feature vectors, the research-purpose
wording, and possible third-party or jurisdiction-specific rights remain unresolved.
CC BY 4.0 permits commercial use only for material within its grant and subject to
its conditions. A commercial deployment requiring definitive clearance may need
confirmation from FMA maintainers or legal counsel. The attribution notice does not
set or authorize `QUARTO_FMA_LICENSE_APPROVED=1`; the FMA archive remains excluded
from the source snapshot.

Cell C also searches at most 1,024 consecutive public seeds beginning at 1729. Each
sample is checked against all 91,390 four-attribute combinations. The search stops
at the first sample with at least two valid quartets; it reports counts and public
element identities, never a quartet. Zero, unique, and multiple-quartet samples are
counted separately.

The notebook is a trusted local experiment only. Python code running in the same
kernel can inspect controller memory; the observation builders are not a process
isolation boundary for arbitrary agents.

## Agent decision traces

The tournament harness records one version-1 decision trace per successfully applied
agent action in each match's restricted log. Each snapshot separates the projected
public observation from only the acting agent's private observation. Optional
explanations are recorded only when an agent explicitly returns the structured
`action` envelope; action-only agents remain supported. An explanation is an
agent-provided report, not a claim about private model reasoning.

For JSONL persistence, pass a `JsonlDecisionTraceWriter` to
`TournamentRunner.run_match(..., decision_trace_writer=writer)`. Each line contains
the match ID, turn ID, agent ID, observation, action, available feedback, and
available metadata. The current controller reports action acceptance and the next
public observation to the runner; the trace marks that feedback as not immediately
delivered to the acting agent. Traces contain private observations and must be kept
with the restricted match artifacts, not published. A write failure is listed in
the restricted result and does not change the accepted action or match outcome.

## Official Benchmark Results (v1.0 — Balanced 2-Game Series)

Executed on Kaggle Benchmarks (`hidden-information-quarto-arena`, Version 7, Run #7) with alternating starting players (`player_1` in Game 1, `player_2` in Game 2), deterministic rule adjudication, and unbiased automated evaluation:

| Model Role | Model Identifier | Wins | Win Rate | Arena Composite Index | Blunder Avoidance | Strategic Trap Rate | Hidden Trait Discovery | Self-Bit Alignment |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Player 1** | `google/gemini-3.8-flash` | 0 / 2 | 0.00 | **38.83** | 0.8667 | 0.00 | 0.00 | 0.3750 |
| **Player 2** | `anthropic/claude-sonnet-4-6@default` | 2 / 2 | 1.00 | **79.64** | 1.0000 | 0.25 | 0.50 | 0.5714 |

### Key Analytical Findings
- **Strategic Trap Exploitation vs. Defensive Blunders:** `claude-sonnet-4-6` actively set `Strategic Traps` (`0.25` trap rate) by handing pieces that completed its private FMA feature lines (`fma:rmse:min:01` in Game 1; `fma:spectral_centroid:kurtosis:01` in Game 2), whereas `gemini-3.8-flash` committed `2` placement blunders by attempting to block 3-piece opponent lines on the 4th cell—unintentionally completing the opponent's hidden Quarto condition.
- **Series Aggregation & Reliability:** Both games completed within a single balanced series (`396.3s` and `227.3s`, zero timeouts, zero failed calls) and aggregated cleanly into `evaluator.series_aggregate`.

## Final Release Artifacts (`final_release_v1/`)

- `Hidden_information_-_Quarto_Arena-run_id_Run_1_google_gemini-3.8-flash.run.json`: Official Kaggle Benchmarks execution artifact.
- `quarto_arena_results.json`: Structured series & per-game evaluation payload.
- `quarto_arena_leaderboard.csv`: Summary leaderboard table for model comparison.
- `quarto_match_visualizer.html`: Standalone interactive HTML replay & telemetry visualizer.
