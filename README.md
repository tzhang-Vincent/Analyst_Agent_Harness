# 金融研究 Agent · Financial Research Agent

> An agentic harness that lets analysts ask questions in natural language and get back **summaries and comparison tables whose every number traces to the SEC filing it came from**. It targets the single most dangerous failure mode in finance: **hallucinated numbers**.
>
> 一个 agentic harness：分析师用自然语言提问，得到**摘要 + 对比表，且每个数字都能追溯到它来自的 SEC 文件**。它专门针对金融场景最致命的问题——**LLM 幻觉出的数字**。

## 核心思想 / The Core Idea

> **Deterministic data + LLM orchestration + full provenance.**
> **确定性数据 + LLM 编排 + 全链路溯源。**

A naive LLM invents plausible numbers from its weights. This harness takes number-generation away from the model entirely:

- every figure is fetched **deterministically from SEC EDGAR's XBRL API**;
- every figure carries a **provenance** record (ticker, CIK, XBRL tag, accession number, clickable URL);
- the LLM only **understands the question, decides what to fetch, and arranges the numbers into prose**;
- a **verifier gate** deletes any number with no backing fact or wrong attribution.

裸 LLM 从模型权重里"编"数字，看起来合理但是错的。这个 harness 把"生成数字"这件事从 LLM 手里彻底拿走：

- 所有财务数字由 **SEC EDGAR 的 XBRL API 确定性抓取**；
- 每个数字背一条 **provenance**（ticker、CIK、XBRL tag、文件编号、可点击链接）；
- LLM 只负责**理解问题、决定抓什么、把数字组织成摘要**；
- 一个 **verifier 终检**：无来源或归属错的数字，直接从答案里删掉。

## 快速开始 / Quick Start

```bash
python3 -m venv .venv
.venv/bin/pip install -e .            # or: pip install -r requirements.txt

# deterministic mode — runs with no API key at all
.venv/bin/agent "NVDA revenue and net income last 2 quarters" -o out.xlsx --no-llm
```

For LLM-written summaries (optional), create a `.env` (see `.env.example`). DeepSeek exposes an **Anthropic-compatible endpoint**, so `provider=anthropic` drives it directly:

```bash
LLM_PROVIDER=anthropic
LLM_MODEL=deepseek-v4-pro
LLM_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_API_KEY=<your-key>
```

Agent mode (LLM-driven tool calls) is the default; with no key it degrades to the deterministic pipeline.

要 LLM 摘要（可选），建 `.env`（见 `.env.example`）配 key。DeepSeek 提供 **Anthropic 兼容端点**，可用 `provider=anthropic` 直接驱动。默认走 **agent 模式**（LLM 自主工具调用）；没配 key 时自动降级为确定性 pipeline。

## 使用示例 / Examples

```bash
.venv/bin/agent "compare NVDA and AMD revenue over the last 4 quarters"   # agent mode (default) / agent 模式（默认）
.venv/bin/agent "NVDA financial health" --mode pipeline                   # snapshot → latest period / 快照类，只取最新一期
.venv/bin/agent "MSFT annual revenue for the last 2 fiscal years" --no-llm
.venv/bin/agent "compare NVDA AMD INTC net income" -o out.xlsx
```

The Excel export has two sheets: **Comparison** (company × metric grid, each value cell hyperlinked to its filing) and **Provenance** (one row per number, 17 columns: ticker, metric, period, value, unit, XBRL tag, accession, filing date, source_url, …), so an analyst can double-check cell by cell.

Excel 导出含两个 sheet：**Comparison**（公司×指标对比表，数值格内嵌超链接）+ **Provenance**（每个数字一行，17 列溯源字段），分析师可逐格核对。

## 设计决策 / Design Decisions

**1. Provenance is a first-class type / Provenance 是一等公民。**
`Provenance` (in `src/agent/schema.py`) rides on every fact; a number without a source is never emitted.
`Provenance` 挂在每个 fact 上，没有来源的数字根本不会产生。

**2. Deterministic data layer / 确定性数据层（`src/agent/extractor.py`）。**
Talks to SEC EDGAR directly (rate-limited, cached, required User-Agent) and handles the real-world data traps: **synonym XBRL tags** (companies switch tags — NVDA moved revenue from `...ExcludingAssessedTax` back to `Revenues`); **restatements** (keep the latest-filed value); **fiscal vs calendar years** (infer the fiscal year-end month so "Q2 FY2026" is labeled correctly); **instant vs duration facts** (balance-sheet points vs income-statement flows, the latter also dropping YTD cumulative facts).
直连 SEC EDGAR，处理真实数据的坑：同义 tag 切换、重述取最新 filed、财年标签、时点型/期间型（顺带剔除 YTD 累计数）。

**3. Tools vs skills, two layers / 工具 vs 技能，两层。**
Tools are atomic data primitives; skills (`src/agent/skills.py`) are reusable analyst recipes bundling sector knowledge + a tool sequence + an output template. Users add YAML recipes in `skills/` — this is where sector specialization and adaptation over time live.
工具是原子数据原语；技能是可复用分析师配方（行业知识 + 工具序列 + 输出模板），用户可在 `skills/` 加 YAML——行业专精和随使用演进的落点。

**4. Two run modes / 两种运行模式。**
`--mode agent` (default) is a true agent loop: the LLM gets tool definitions and *decides* which to call, the harness runs deterministic extraction and returns the facts, looping until the LLM writes the final answer. `--mode pipeline` is deterministic orchestration (intent → extract → summarize → verify). Both share the same data layer and verifier.
`--mode agent`（默认）是真正的 agent loop；`--mode pipeline` 是确定性编排的固定流水线。两者共享数据层和 verifier。

**5. Verifier double-check / Verifier 双重校验（`src/agent/verifier.py`）。**
① **Fabrication** — a number not close to any fact; ② **Attribution** — a number attached to the wrong company/metric ("AMD revenue $96B" when it is NVDA's). In agent mode the verifier runs *inside* the loop as a mandatory feedback step (the LLM cannot skip it) and a hard gate sanitizes whatever survives.
①编造（数字不在任何 fact 里）②归属错（数字挂在错误的公司/指标上）。agent 模式里循环内强制反馈 + 循环外硬闸兜底。

**6. LLM intent parsing + deterministic fallback / LLM 解析意图 + 确定性兜底。**
Intent is LLM-first for flexible phrasing ("profitability" → `net_income`), but every LLM ticker/metric is validated against the SEC map and the metric registry, with the rule parser as fallback — an LLM mis-parse cannot inject a wrong company or metric.
意图解析 LLM 优先，但每个输出都过 SEC/词表校验，规则解析兜底。

**7. User preference memory / 用户偏好记忆（`src/agent/profile.py`）。**
Three JSON memories — preferences (watchlist, preferred metrics), interactions (query history, corrections), knowledge — persisted incrementally after each query, so new tickers join the watchlist and frequently-used metrics are prioritized.
三类 JSON 记忆（偏好/交互/领域知识），每次查询后增量写回。

## 溯源机制 / Provenance

Three renderings form a "verifiable" loop / 三处呈现形成"可核对"闭环：

| 场景 / Where | 呈现 / How |
|---|---|
| CLI | `[n]` inline references after numbers + **clickable** numbered Sources (OSC 8 hyperlinks) |
| Excel | Comparison cells hyperlinked + Provenance sheet (17 columns) |
| CSV | flat, with a source_url column |

The `[n]` numbering is maintained by the **harness** (not the LLM) — the LLM only sees the numbers, never the URLs, so it cannot fabricate provenance.
`[n]` 编号表由 **harness 维护**，LLM 只看到编号、看不到 URL，无法编造来源。

## 评测 / Evaluation

**Controlled comparison**: same model `deepseek-v4-pro`, harness on vs off, 15 questions (cross-quarter / cross-company / single-metric / annual), all against the same EDGAR oracle (the deterministic extractor's ground truth):

**受控对比**：同一模型，只变 harness 开/关，15 题四类，都对比同一份 EDGAR oracle：

| Metric / 指标 | agent | pipeline | bare LLM / 裸 LLM |
|---|---|---|---|
| Coverage (recall) / 覆盖率 | 100% | 100% | ~11% |
| Precision (no extra values) / 精度 | 100% | 100% | — |
| Provenance coverage / 溯源覆盖率 | 100% | 100% | 0% |
| Intent accuracy / 意图准确率 | — | 100% | — |
| Numbers the verifier caught / 被拦截数字 | 0 | 0 | all / 全部 |

```bash
.venv/bin/python -m eval.run_eval                  # pipeline (LLM intent + summary)
.venv/bin/python -m eval.run_eval --mode agent     # agent mode
.venv/bin/python -m eval.run_eval --baseline       # + bare-LLM baseline
.venv/bin/python -m eval.run_eval --baseline --limit 5   # quick subset
```

Coverage and precision are reported together because **coverage alone misses "right answer plus extra wrong ones"** (a ticker leak). The bare LLM's ~11% is a few memorized figures; the harness is deterministic, so 100% with full provenance. The metric is strict (±1% on exact figures), so "around $100B" scores 0 — analysts need exact, traceable numbers.
**coverage 和 precision 要一起看**——只测 coverage 会漏掉"答对了又答多了"。裸 LLM 的 ~11% 是蒙对知名数字，其余 0%；harness 确定性抓取，每次 100% 且可溯源。指标按 ±1% 精确匹配。

## 项目结构 / Project Layout

```
src/agent/
  analyst.py     Analyst: mode dispatch (pipeline vs agent) / 模式分发
  pipeline.py    pipeline mode: deterministic orchestration / 确定性编排
  agent_loop.py  agent mode: LLM tool-call loop + in-loop verify / 工具循环+循环内校验
  extractor.py   deterministic extraction (shared; correctness core) / 确定性抓取
  verifier.py    fabrication + attribution checks / 校验：编造+归属
  edgar.py       SEC EDGAR client / SEC 客户端
  schema.py      Provenance / Fact / QueryIntent / Answer
  metrics.py     metric → XBRL tag synonym registry / 指标映射
  skills.py      analyst recipes (builtin + user YAML) / 分析师配方
  profile.py     user preference memory / 用户记忆
  table.py       terminal table + xlsx/csv export / 导出
  llm.py         provider-agnostic LLM (anthropic/openai/deepseek)
  cli.py         CLI entry / 入口
eval/            questions, oracle, runner, metrics / 评测
tests/           64 tests / 64 个测试
```

## 已知限制 / Known Limitations

- **Fiscal Q4 across the calendar-year boundary** — companies whose fiscal year straddles Dec 31 (NVDA ends late January) may lack a discrete Q4 flow fact; provenance's start/end dates always disambiguate. / 财年跨自然年的公司（NVDA 财年 1 月底结束）有时缺单独的 Q4 期间型 fact。
- **Cross-company quarter misalignment** — different fiscal year-ends; the table keeps each company's periods in separate columns rather than conflating them. / 不同公司财年结束月不同，对比表按各自精确日期分列。
- **Companies that don't file a tag** — e.g. AMD files `LiabilitiesAndStockholdersEquity` but not `Liabilities`; the harness returns "no data" rather than a wrong number. / 如 AMD 不单独披露 `Liabilities`，harness 返回"无数据"而非用错数。
- **Deterministic ticker parsing** — filters common English/financial words; single-letter tickers ("V") or tickers that are also financial words ("CASH", "NET") need the full name or the watchlist. / 单字符 ticker 或与金融词重合的 ticker 需用全名或加入 watchlist。
- **Attribution check is line-granular** — a swapped pair of numbers inside one line isn't caught; finer detection needs clause-level splitting. / 归属校验是行粒度，一行内多公司多数字的对调分辨不出。
