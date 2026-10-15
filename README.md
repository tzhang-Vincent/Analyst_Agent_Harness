# Financial Research Agent — provenance-tracked analysis over SEC EDGAR

An agentic harness that lets a financial analyst ask questions in natural
language and get back **summaries and comparison tables whose every number
traces to the exact SEC filing it came from**. It is designed to beat a bare
chatbot on the specific failure that matters in finance: **hallucinated
numbers**.

## The one idea

> **Deterministic data, LLM orchestration, full provenance.**

A naive LLM answers financial questions from its weights, so it invents
plausible-looking numbers. This harness takes number generation away from the
model entirely:

- Every figure is fetched **deterministically from SEC EDGAR's XBRL API**.
- Every figure carries a **provenance record**: ticker, CIK, XBRL tag,
  fiscal period, filing accession number, filing date, and a clickable
  `sec.gov` URL.
- The LLM's only jobs are to parse the question, pick which tools to call, and
  *arrange* the fetched numbers into prose — and a **verifier** re-checks that
  no number appears in the answer that is not backed by a fetched fact.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -e .            # or: pip install -r requirements.txt

# deterministic mode — works with no API key at all
.venv/bin/agent "compare NVDA AMD revenue and net income over the last 4 quarters" -o out.xlsx
```

For LLM-written summaries (optional), create a `.env` (see `.env.example`) with
an API key and set `LLM_PROVIDER` / `LLM_MODEL`:

```bash
export LLM_PROVIDER=anthropic      # anthropic | openai | deepseek
export LLM_MODEL=deepseek-v4-pro   # or claude-sonnet-5-5, gpt-4o, ...
export ANTHROPIC_API_KEY=...
.venv/bin/agent "summarize NVDA's revenue trend"        # now uses the LLM for prose
```

DeepSeek exposes an **Anthropic-compatible endpoint**, so `provider=anthropic`
can drive it directly by pointing `LLM_BASE_URL` there:

```bash
export LLM_PROVIDER=anthropic
export LLM_MODEL=deepseek-v4-pro
export LLM_BASE_URL=https://api.deepseek.com/anthropic
export ANTHROPIC_API_KEY=<deepseek-key>
```

The deterministic mode is the default safety path: it needs no key and cannot
hallucinate. `--no-llm` forces it explicitly.

## Examples

```
.venv/bin/agent "NVDA revenue and net income last 4 quarters" -o nvda.xlsx
.venv/bin/agent "compare NVDA AMD INTC revenue over the last 4 quarters"
.venv/bin/agent "MSFT annual revenue and net income for the last 2 fiscal years"
```

The Excel export contains two sheets:

- **Comparison** — one row per company×metric, one column per quarter, each
  value cell hyperlinked to its filing.
- **Provenance** — one row per number: metric, period, value, unit, XBRL tag,
  accession number, filing date, and source URL. An analyst can double-check
  any cell against the original 10-Q/10-K.

## Design decisions

**1. Provenance is a first-class type.** `Provenance` (see `src/agent/schema.py`)
is attached to every fact. A number without provenance is simply never emitted.

**2. Deterministic data layer.** `src/agent/edgar.py` + `extractor.py` hit SEC
EDGAR directly (rate-limited, cached, with the required User-Agent). The
extractor handles the real-world data-quality problems that break naive agents:

- **Synonym XBRL tags** — companies switch tags (NVDA moved recent revenue from
  `RevenueFromContractWithCustomerExcludingAssessedTax` back to `Revenues`).
  Each metric maps to an ordered synonym list, and the extractor picks the tag
  the company is *currently* filing (the one with the newest data).
- **Restatements** — the same quarter can appear multiple times; the extractor
  keeps the *latest-filed* value.
- **Fiscal vs. calendar periods** — `frame` labels are calendar-based and
  mislabel fiscal quarters for companies whose year does not end in December
  (NVDA, MSFT, …). The extractor infers the fiscal year-end month and labels
  quarters as `Q2 FY2026` from the company's own `fp` + the end date.
- **Duration vs. instant facts** — income/cash-flow are flows (filter by ~13-week
  duration, which also drops YTD/9M cumulative facts); balance-sheet items are
  point-in-time (classified by `fp`, with the fiscal-year-end instant treated as
  Q4).

**3. Tools vs. skills, deliberately two layers.** *Tools* are the atomic
deterministic primitives (`get_income_statement`, `compare_companies`, …). *Skills*
(`src/agent/skills.py`) are reusable analyst recipes that bundle sector knowledge
(which metrics matter — e.g. R&D intensity for semiconductors), a tool sequence,
and an output template. Users add their own YAML recipes in `skills/`, so the
agent accumulates capability over time.

**4. The agent adapts to the user.** `src/agent/profile.py` keeps three JSON
memories — preferences (watchlist, preferred metrics), interactions (past
queries, user corrections), and knowledge — loaded before answering and
updated after, so a semiconductor analyst who keeps asking for R&D intensity
sees that metric prioritized.

**5. Verifier as a final gate.** `src/agent/verifier.py` extracts every numeric
claim from the answer and drops anything not backed by a fetched fact. A data
gap produces "no data", never a guess.

**6. LLM intent parsing with a deterministic safety net.** When an LLM is
configured, it parses the question first — this handles phrasing the rule parser
cannot ("profitability" → `net_income`). Every LLM ticker/metric is then validated
against the SEC ticker map and the metric registry, and the deterministic rule
parser is the fallback, so a mis-parse can never inject a wrong company or metric.

**7. Two run modes.** `--mode pipeline` (default) is deterministic orchestration
with the LLM at fixed steps (intent + summary). `--mode agent` is a true agent
loop: the LLM is given tool definitions and *decides* which tool to call, the
harness executes the deterministic extraction and returns the facts, and the loop
repeats until the LLM writes the final answer. In agent mode the verifier runs
*inside* the loop as a mandatory feedback step — the LLM cannot skip it — so an
unsupported number (e.g. a gap the LLM computed) is fed back and the LLM revises.
A final hard gate still sanitizes whatever remains.

## Evaluation

`eval/` measures the **full harness — the LLM wired in** (intent parsing +
deterministic EDGAR extraction + LLM-written summary + the verifier gate) —
against the EDGAR oracle, over a 15-question set spanning cross-quarter,
cross-company, single-metric, and annual queries:

Both modes are measured over the same 15-question set against the EDGAR oracle
(`deepseek-v4-pro` via its Anthropic-compatible endpoint, thinking disabled):

| Metric | pipeline | agent | bare LLM |
|---|---|---|---|
| Coverage (recall: oracle values present) | **100%** | **100%** | **11%** |
| Precision (no extra wrong values) | **100%** | **100%** | — |
| Provenance coverage | **100%** | **100%** | 0% |
| Intent accuracy (LLM parsed right tickers/metrics) | **100%** | — (LLM drives tools) | — |
| Unsupported numbers the verifier caught | **0** | **0** | (all) |

Coverage and precision are reported together because **coverage alone is not
enough**: it would miss "the harness returned the right numbers *plus* extra
wrong ones" (a ticker/metric leak). Precision catches that.

In agent mode the verifier runs inside the loop as a mandatory feedback step, so
the LLM revises any derived value (a gap or growth rate it computed) into a
ratio or drops it — hence 0 unsupported numbers survive to the final answer. The
bare LLM answering from memory hits ~11% (mostly 0%, with a few memorized figures
for well-known companies) — a ~9× gap that is the whole point of the harness. The
metric is strict (±1% on exact per-quarter figures), so "around $100B" scores 0:
analysts need exact, traceable numbers.

```bash
.venv/bin/python -m eval.run_eval                  # full harness (LLM summary)
.venv/bin/python -m eval.run_eval --baseline       # + bare-LLM baseline
.venv/bin/python -m eval.run_eval --baseline --limit 5   # quick subset
```

The oracle is built with the same deterministic extractor straight from EDGAR.
The harness matches it exactly because it *is* that deterministic path. The
interesting number is the **baseline**: a bare LLM answering from memory has no
way to pull a real filing, so its accuracy collapses — that is the whole point
of the harness. The comparison is controlled: same model, harness on vs. off.

## Project layout

```
src/agent/
  schema.py     Provenance / Fact / QueryIntent / Answer
  edgar.py      SEC EDGAR client (rate-limited, cached, User-Agent)
  extractor.py  deterministic fact extraction (synonyms, restatements, fiscal labels)
  metrics.py    metric -> XBRL tag registry
  tools.py      data primitives (income statement, balance sheet, compare, ...)
  skills.py     analyst recipes (builtin + user YAML)
  agent.py      intent -> skill -> tools -> summary -> verify -> memory
  verifier.py   no number ships unless backed by a fact
  table.py      terminal table + xlsx/csv export with provenance
  profile.py    user preference memory
  llm.py        provider-agnostic LLM (anthropic/openai/deepseek)
  cli.py        argparse CLI
eval/           questions, oracle, runner, report
tests/          41 tests (data layer, tables, memory, skills, verifier, agent)
```

## Known limitations

- **Fiscal Q4 across a calendar-year boundary.** For companies whose fiscal year
  straddles Dec 31 (NVDA ends late January), SEC sometimes omits the discrete
  Q4 flow fact; provenance's `start`/`end` dates always disambiguate.
- **Cross-company quarter alignment.** Companies have different fiscal year-ends,
  so "Q2 FY2026" is not the same calendar period for NVDA and AMD. The comparison
  table keeps each company's periods in separate columns rather than conflating
  them; exact dates are in the Provenance sheet.
- **Companies that don't file a tag.** E.g. AMD does not file a standalone
  `Liabilities` concept (only `LiabilitiesAndStockholdersEquity`); the harness
  returns "no data" rather than substitute a wrong number.
- **Deterministic ticker parsing.** Intent parsing is rule-based for reliability;
  it filters common English/function words and financial terms from ticker
  candidates. Rare single-letter tickers ("V") or tickers that are also financial
  words ("CASH", "NET") should be queried by full name or added to the watchlist.
- **Bare-LLM baseline** requires an API key; without one, `--baseline` is a
  no-op.
