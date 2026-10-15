# 金融研究 Agent · Financial Research Agent

A research agent for equity analysts that answers questions about public financial statements — and makes every number it states traceable back to the exact SEC filing it came from.

面向股票分析师的金融研究 agent：能回答关于公开财报的问题，而且说出的每一个数字都能追溯到它来自的哪一份 SEC 文件。

---

## 为什么做这个 / Why this exists

Ask a bare LLM for NVIDIA's quarterly revenue and it will happily produce a number — confident, plausible, and sometimes flat wrong. For most uses that's a nuisance. For someone deciding whether to buy a stock, it's dangerous. The problem isn't that the model is "careless"; it's that it has no source of truth, so under pressure it fills the gap from its weights.

直接问一个裸 LLM"英伟达上季度营收多少"，它会自信地给出一个数字——看起来合理，但有时是错的。对大多数场景这只是烦人；对做投资决策的人来说，这是危险。问题不在于模型"粗心"，而在于它没有事实来源，一旦被追问就只能从权重里"编"。

The task here was to build an **agentic harness** that outperforms a bare chatbot on exactly this failure mode. My answer boils down to one move: **don't ask the LLM to be more careful — take number-generation away from it entirely.**

这个任务要求构建一个 **agentic harness**，恰恰要在"幻觉数字"这个失败模式上击败裸聊天机器人。我的答案归结为一句话：**不要指望 LLM 更小心——而是把"生成数字"这件事从它手里彻底拿走。**

## 核心思想 / The core idea

> **Deterministic data, LLM orchestration, full provenance.**
> **确定性数据 + LLM 编排 + 全链路溯源。**

Every number in the answer is fetched **deterministically from SEC EDGAR's XBRL API**. The LLM's job is limited to three things: understand the question, decide which data to fetch, and turn the fetched numbers into readable prose. It never has the opportunity to invent a figure, because it's only ever handed real ones.

答案里的每个数字都由 **SEC EDGAR 的 XBRL API 确定性抓取**。LLM 只做三件事：理解问题、决定抓什么、把抓到的数字组织成可读的摘要。它根本没有机会编数字，因为它拿到的从来都是真实的数。

Two guarantees fall out of this design:

这个设计带来两个保证：

1. **Correctness is architectural, not aspirational.** The numbers are right because they came from EDGAR, not because the model "tried hard".
   **正确性是架构保证的，不是"模型努力"的结果**——数字对，是因为它来自 EDGAR。
2. **Every number carries provenance.** A `Provenance` record — ticker, CIK, XBRL tag, fiscal period, filing accession number, filing date, and a clickable sec.gov URL — rides on every fact. If you can't click through to the source, the number doesn't ship.
   **每个数字都带溯源**——`Provenance` 记录（ticker、CIK、XBRL tag、财季、文件编号、提交日期、可点击的 sec.gov 链接）挂在每个 fact 上。点不到来源的数字，根本不会出现。

## 实际长什么样 / What it looks like

A query and its output in the terminal:

一条查询和它在终端里的输出：

```
$ agent "NVDA revenue and net income last 2 quarters"

NVIDIA (NVDA) results for the last two quarters:

| Period    | Revenue  | Net Income |
|-----------|----------|------------|
| Q1 FY2027 | $81.6B [1] | $58.3B [1] |
| Q2 FY2027 | $96.2B [2] | $59.7B [2] |

Sources (clickable)
  [1] https://www.sec.gov/Archives/edgar/data/1045810/000104581026000052/...
  [2] https://www.sec.gov/Archives/edgar/data/1045810/000104581026000075/...
```

The `[1]` / `[2]` markers next to the numbers link to the Sources list, where each URL is **clickable** in the terminal (Cmd-click). The same answer exported to Excel has two sheets: the comparison grid (each value cell hyperlinked to its filing) and a `Provenance` sheet with one row per number and 17 columns of traceability — tag, accession, filing date, and the URL.

数字旁的 `[1]`/`[2]` 对应下面的 Sources 列表，终端里 URL **可点击**（Cmd+点击）。导出到 Excel 后有两个 sheet：对比表（每个数值格内嵌超链接）+ `Provenance` sheet（每个数字一行、17 列溯源字段：tag、文件编号、提交日期、URL）。

## 快速开始 / Getting started

```bash
python3 -m venv .venv
.venv/bin/pip install -e .            # or: pip install -r requirements.txt

# deterministic mode — no API key needed at all
.venv/bin/agent "NVDA revenue and net income last 2 quarters" -o out.xlsx --no-llm
```

For LLM-written summaries, create a `.env` (see `.env.example`). DeepSeek exposes an Anthropic-compatible endpoint, so `provider=anthropic` drives it directly:

要 LLM 摘要，建 `.env`（见 `.env.example`）。DeepSeek 提供 Anthropic 兼容端点，用 `provider=anthropic` 直接驱动：

```bash
LLM_PROVIDER=anthropic
LLM_MODEL=deepseek-v4-pro
LLM_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_API_KEY=<your-key>
```

Then run it in agent mode — the LLM decides which data to fetch, so it handles open-ended questions, not just "extract metric X":

配好 key 后即可跑 agent 模式——LLM 自己决定抓什么数据，所以能处理开放式问题，不只是"抓 X 指标"：

```bash
.venv/bin/agent "compare NVDA and AMD revenue over the last 4 quarters"
.venv/bin/agent "which of NVDA, AMD and INTC grew revenue fastest last quarter?"
.venv/bin/agent "is NVDA's balance sheet healthy?"
```

Agent mode (LLM-driven tool calls) is the default; with no key it degrades to the deterministic pipeline.

默认走 agent 模式（LLM 自主工具调用）；没配 key 时自动降级为确定性 pipeline。

## 我实际踩过的数据坑 / The data problems I actually hit

This is where most of the real work went, and where a naive agent fails silently. SEC XBRL data is *messy*, and getting "the right number" means handling each of these:

大部分工作量在这里，也是朴素 agent 会静默出错的地方。SEC 的 XBRL 数据很"脏"，要拿到"正确的数"就得逐个处理：

**Synonym XBRL tags.** Companies switch the tag they report under. NVIDIA's revenue lives in `RevenueFromContractWithCustomerExcludingAssessedTax` through 2021, then moves back to plain `Revenues`. A naive agent that grabs "the first tag with enough data" returns 2019 numbers. My extractor picks the tag the company is *currently* filing — the one with the newest data.
**同义 XBRL tag。** 公司会换上报用的 tag。英伟达的营收在 2021 年前用 `RevenueFromContractWithCustomerExcludingAssessedTax`，之后换回了简单的 `Revenues`。朴素 agent 若"取第一个数据够多的 tag"，会拿到 2019 年的旧数。我的 extractor 选的是公司*当前实际在用*的 tag（最新数据最靠前的那个）。

**Restatements.** The same quarter appears multiple times — once in the original 10-Q, again restated in a later 10-K. You want the latest-filed value, not the original one.
**重述。** 同一个季度会出现多次——原始 10-Q 报一次，后面的 10-K 再重述一次。要取的是 filed 最新的值，不是原始的。

**Fiscal vs calendar years.** NVIDIA's fiscal year ends in late January, so SEC's calendar-quarter labels mislabel its fiscal quarters. "Q2 FY2026" is not what a calendar frame says. I infer the fiscal year-end month from annual filings and label periods from the end date instead of trusting the frame.
**财年 vs 自然年。** 英伟达财年 1 月底结束，SEC 的自然年标签会把它的财季标错。"Q2 FY2026" 并不是自然年 frame 说的那样。我从年报推断财年结束月，用结束日期给期间贴标签，而不是信 frame。

**Instant vs duration facts.** Balance-sheet items (assets, cash) are point-in-time; income-statement items are flows over a period. Filter by ~13-week duration and you correctly drop YTD cumulative facts (6-month, 9-month) — but you'd also throw away every balance-sheet number. The extractor treats the two kinds separately.
**时点型 vs 期间型。** 资产负债表项目（资产、现金）是时点；利润表项目是一段时间的流量。按 ~13 周时长过滤，能正确剔除 YTD 累计数（6 个月、9 个月），但也会把资产负债表数据全丢掉——所以 extractor 把两类分开处理。

**Companies that don't file a tag.** AMD doesn't report a standalone `Liabilities` concept (only `LiabilitiesAndStockholdersEquity`). The right answer here is "no data", not a substitute number — and that's what the harness returns.
**公司不披露某个 tag。** AMD 不单独披露 `Liabilities`（只有 `LiabilitiesAndStockholdersEquity`）。正确答案是"无数据"，而不是拿别的数顶替——harness 就是这么做的。

## 两种模式，各管一类问题 / Two modes, two kinds of questions

**Agent mode** (default) is a genuine agent loop. The LLM is given tool definitions (`get_metrics`, `compare_companies`) and *decides* which to call and with what arguments; the harness executes the deterministic extraction and hands the facts back; the loop repeats until the LLM writes a final answer. This handles open-ended, multi-step, or implicit questions — "which of these companies grew revenue fastest?", "is NVDA's balance sheet healthy?" — that a fixed pipeline can't express.

**Agent 模式**（默认）是真正的 agent loop。LLM 拿到工具定义，*自己决定*调哪个、传什么参数；harness 执行确定性抓取并把结果交回；循环到 LLM 写出最终答案。它能处理开放式、多步、或隐含的问题——"这几家谁营收增长最快？""英伟达资产负债表健康吗？"——这些固定流水线表达不了。

**Pipeline mode** (`--mode pipeline`) is deterministic orchestration — parse intent, fetch, summarize, verify, in a fixed sequence. It's the cheap, reproducible, offline-capable baseline: simple "extract these metrics" queries are faster and can run with no LLM at all (`--no-llm`). It's also what the eval uses as its reference/oracle.

**Pipeline 模式**（`--mode pipeline`）是确定性编排——解析意图、抓取、摘要、校验，固定顺序。它是便宜、可复现、能离线的底座：简单的"抓这些指标"查询更快，而且 `--no-llm` 完全不用 LLM。评测也拿它当参照/oracle。

A detail worth noticing: even in agent mode, the verifier runs *inside* the loop as a mandatory step the LLM can't skip — after each draft answer it checks every number, and if any is fabricated or attributed to the wrong company, that's fed back for a rewrite. So "agentic" here never means "unsupervised".

值得注意的一点：即使在 agent 模式，verifier 也在循环内作为 LLM 无法跳过的强制步骤运行——每写完一版答案就逐个检查数字，只要有编造或归属错就喂回去重写。所以这里的"agentic"绝不等于"无人监督"。

## 校验：不只查"数字在不在"，还查"挂在谁头上" / The verifier

Two checks, both against the deterministic facts:

两道检查，都以确定性 fact 为基准：

- **Fabrication** — a number not close to any fetched fact (a hallucinated or derived figure).
  **编造**——数字不在任何抓取的 fact 值附近（幻觉或推算值）。
- **Attribution** — a number that exists, but is attached to the wrong company/metric in the prose ("AMD revenue $96B" when $96B is NVIDIA's). The verifier splits the text into claims, detects which tickers/metrics each line names, and requires the number to match a fact for *those* entities.
  **归属错**——数字存在，但挂在错误的公司/指标上（"AMD 营收 $96B"，其实是英伟达的）。verifier 把文本拆成行，检测每行提到的 ticker/指标，要求数字匹配*那些*实体的 fact。

Anything that fails either check is physically removed from the answer, not just flagged.

任何一道没过，数字就被从答案里物理删除，不是只标个警告。

## 评测：怎么证明它"击败了 ChatGPT" / How I measured it

The comparison is **controlled**: the same model (`deepseek-v4-pro`), with the harness on vs off, over 15 questions spanning cross-quarter, cross-company, single-metric, and annual queries. Everything is measured against an oracle — the deterministic extractor applied to each question's ground-truth spec, i.e. the correct answer.

对比是**受控的**：同一模型（`deepseek-v4-pro`），harness 开 vs 关，15 道题（跨季度/跨公司/单指标/年度），都对比同一份 oracle——即确定性 extractor 按题目真值 spec 取出的正确答案。

| Metric | agent | pipeline | bare LLM |
|---|---|---|---|
| Coverage (recall) | 100% | 100% | ~11% |
| Precision (no extra wrong values) | 100% | 100% | — |
| Provenance coverage | 100% | 100% | 0% |
| Intent accuracy | — | 100% | — |
| Numbers the verifier caught | 0 | 0 | (all) |

The two numbers I'd point to in an interview: **coverage *and* precision, together.** Coverage alone is flattering — it would have missed the ticker-leak bug (fetching the right numbers *plus* an extra wrong company), which precision caught. And the bare LLM's ~11% is telling: it's a handful of memorized figures for famous companies, zero on everything else. The harness is 100% every time because it's deterministic, and 100% of its numbers are traceable.

面试时我会指出的两个数字：**coverage 和 precision 要一起看**。只测 coverage 是讨好的——它会漏掉"答对了又答多了"（ticker 泄漏 bug 就是这么被 precision 抓到的）。而裸 LLM 的 ~11% 很能说明问题：那是对知名公司的几个背下来的数字，其余全是 0。harness 每次 100%，因为它是确定性的，而且每个数字都可溯源。

```bash
.venv/bin/python -m eval.run_eval                  # pipeline (LLM intent + summary)
.venv/bin/python -m eval.run_eval --mode agent     # agent mode
.venv/bin/python -m eval.run_eval --baseline       # + bare-LLM baseline
```

## 诚实的局限 / Honest limitations

- **Fiscal Q4 across the calendar-year boundary** — companies whose fiscal year straddles Dec 31 (NVIDIA ends late January) sometimes have no discrete Q4 flow fact; provenance's start/end dates always disambiguate. / 财年跨自然年的公司（英伟达 1 月底结束）有时缺单独的 Q4 期间型 fact；起止日期始终可消歧。
- **Cross-company quarter misalignment** — companies have different fiscal year-ends, so "Q2 FY2026" isn't the same calendar period for NVDA and AMD; the table keeps each company's columns separate rather than conflating them. / 不同公司财年结束月不同，"Q2 FY2026"对 NVDA 和 AMD 不是同一日历区间；对比表按各自日期分列，不强行对齐。
- **Attribution is line-granular** — a swapped pair of numbers inside one line isn't caught; finer detection would need clause-level splitting. / 归属校验是行粒度，一行内两个数字对调分辨不出，更细要拆到从句级。
- **Deterministic ticker parsing** — single-letter tickers ("V") or tickers that are also financial words ("CASH", "NET") need the full name or the watchlist. / 单字符 ticker 或与金融词重合的 ticker（"CASH"/"NET"）需用全名或加入 watchlist。

## 项目结构 / Project layout

```
src/agent/
  analyst.py     Analyst: dispatches pipeline vs agent
  pipeline.py    pipeline mode: deterministic orchestration
  agent_loop.py  agent mode: LLM tool-call loop + in-loop verifier
  extractor.py   deterministic extraction (shared; the correctness core)
  verifier.py    fabrication + attribution checks
  edgar.py       SEC EDGAR client (rate-limited, cached, builds filing URLs)
  schema.py      Provenance / Fact / QueryIntent / Answer
  metrics.py     metric → XBRL-tag synonym registry
  skills.py      analyst recipes (built-in + user YAML)
  profile.py     user preference memory (3 JSON files)
  table.py       terminal table + xlsx/csv export
  llm.py         provider-agnostic LLM (anthropic/openai/deepseek)
  cli.py         CLI entry point
eval/            questions, oracle, runner, metrics
tests/           64 tests
```
