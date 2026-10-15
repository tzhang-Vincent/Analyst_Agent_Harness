# 金融研究 Agent —— 带完整溯源追踪的 SEC EDGAR 分析

一个 agentic harness：分析师用自然语言提问，得到**摘要 + 对比表，且每个数字都能追溯到它来自的 SEC 文件**。它专门针对金融场景最致命的问题——**LLM 幻觉出的数字**。

## 核心思想（一句话）

> **确定性数据 + LLM 编排 + 全链路溯源。**

裸 LLM（ChatGPT）从模型权重里"编"数字，看起来合理但是错的。这个 harness 把"生成数字"这件事从 LLM 手里彻底拿走：

- 所有财务数字由 **SEC EDGAR 的 XBRL API 确定性抓取**；
- 每个数字背一条 **provenance**（ticker、CIK、XBRL tag、文件编号、可点击链接）；
- LLM 只负责**理解问题、决定抓什么、把数字组织成摘要**；
- 一个 **verifier 终检**：无来源或归属错的数字，直接从答案里删掉。

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/pip install -e .            # 或 pip install -r requirements.txt

# 纯确定性模式——无需任何 API key 就能跑
.venv/bin/agent "NVDA revenue and net income last 2 quarters" -o out.xlsx --no-llm
```

要 LLM 摘要（可选），建 `.env`（见 `.env.example`）配 key 和模型。DeepSeek 提供了 Anthropic 兼容端点，可直接用 `provider=anthropic` 驱动：

```bash
LLM_PROVIDER=anthropic
LLM_MODEL=deepseek-v4-pro
LLM_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_API_KEY=<你的 key>
```

默认走 **agent 模式**（LLM 自主工具调用）；没配 key 时自动降级为确定性 pipeline。

## 使用示例

```bash
.venv/bin/agent "compare NVDA and AMD revenue over the last 4 quarters"   # agent 模式（默认）
.venv/bin/agent "NVDA financial health" --mode pipeline                   # 快照类问题，只取最新一期
.venv/bin/agent "MSFT annual revenue for the last 2 fiscal years" --no-llm
.venv/bin/agent "compare NVDA AMD INTC net income" -o out.xlsx
```

Excel 导出含两个 sheet：

- **Comparison** —— 公司×指标 对比表，每个数值格**内嵌超链接**指向 filing；
- **Provenance** —— 每个数字一行，17 列（ticker、指标、期间、值、单位、XBRL tag、文件编号、提交日期、source_url 等），分析师可逐格核对。

## 设计决策

**1. Provenance 是一等公民。** `Provenance`（`src/agent/schema.py`）挂在每个 fact 上。没有来源的数字根本不会产生。

**2. 确定性数据层（`src/agent/extractor.py`）。** 直连 SEC EDGAR（限速、缓存、带必需 User-Agent），并处理真实数据的坑：
- **同义 XBRL tag 切换**——公司会换 tag（NVDA 近期营收从 `...ExcludingAssessedTax` 换回 `Revenues`），选取"当前实际在用"的 tag；
- **重述**——同一季度报多次时取 filed 最新值；
- **财年 vs 自然年**——从年报推断财年结束月，正确标出 "Q2 FY2026"（NVDA 财年 1 月底结束）；
- **时点型 vs 期间型**——资产负债表（时点）与利润表/现金流（期间）分开处理，期间型顺带剔除 YTD 累计数。

**3. 工具 vs 技能，两层。** 工具是原子数据原语；技能（`src/agent/skills.py`）是可复用分析师配方，绑"行业知识 + 工具序列 + 输出模板"，用户可在 `skills/` 加 YAML——这是行业专精和随使用演进的落点。

**4. 两种运行模式。** `--mode agent`（默认）是真正的 agent loop：LLM 拿到工具定义，自己决定调哪个、传什么参数，harness 执行确定性抓取并返回结果，循环到 LLM 写出最终答案；`--mode pipeline` 是确定性编排（意图解析 + 抓取 + 摘要 + 校验的固定流水线）。两者共享同一套确定性数据层和 verifier。

**5. Verifier 双重校验（`src/agent/verifier.py`）。** ①**编造**——数字不在任何 fact 值里；②**归属错**——数字存在但挂在错误的公司/指标上（"AMD 营收 $96B"，其实是 NVDA 的）。agent 模式里 verifier 在循环内作为**强制反馈步骤**（LLM 无法跳过）让 LLM 自纠，循环外还有硬闸兜底。

**6. LLM 解析意图 + 确定性兜底。** 意图解析 LLM 优先（能处理"profitability"这类词表外的说法），但每个 LLM 输出的 ticker/指标都过 SEC/词表校验，规则解析做兜底——LLM 解析错也注入不了错误公司/指标。

**7. 用户偏好记忆（`src/agent/profile.py`）。** 三类 JSON 记忆：偏好（watchlist、偏好指标）、交互（历史查询、用户修正）、领域知识。每次查询后增量写回——新 ticker 自动进 watchlist、常用指标优先级提升、模糊查询落到 watchlist。

## 溯源机制

三处呈现，形成"可核对"闭环：

| 场景 | 呈现 |
|---|---|
| CLI | 数字后带 `[n]` 行内引用 + Sources 里**可点击**的编号 URL（OSC 8 超链接） |
| Excel | Comparison 数值格内嵌超链接 + Provenance sheet 17 列 |
| CSV | 扁平化，带 source_url 列 |

`[n]` 编号表由 **harness 维护**（不是 LLM），LLM 只看到编号、看不到 URL，无法编造来源。

## 评测

**受控对比**：同一模型 `deepseek-v4-pro`，只变 harness 开/关，15 道题（跨季度/跨公司/单指标/年度四类），都对比同一份 EDGAR oracle（确定性 extractor 直取的正确答案）：

| 指标 | agent | pipeline | 裸 LLM |
|---|---|---|---|
| 覆盖率（召回） | 100% | 100% | ~11% |
| 精度（无多抓） | 100% | 100% | — |
| 溯源覆盖率 | 100% | 100% | 0% |
| 意图准确率 | — | 100% | — |
| 被 verifier 拦截的数字 | 0 | 0 | 全部 |

```bash
.venv/bin/python -m eval.run_eval                  # pipeline（含 LLM 意图+摘要）
.venv/bin/python -m eval.run_eval --mode agent     # agent 模式
.venv/bin/python -m eval.run_eval --baseline       # + 裸 LLM 基线
.venv/bin/python -m eval.run_eval --baseline --limit 5   # 快速子集
```

要点：**coverage 和 precision 要一起看**——只测 coverage 会漏掉"答对了又答多了"（如 ticker 泄漏）。裸 LLM 的 ~11% 是"凭记忆蒙对知名数字"，其余 0%；harness 是确定性抓取，每次 100% 且可溯源。指标按 ±1% 精确匹配，所以"大概 $100B"直接判 0——分析师要的是精确可溯源数字。

## 项目结构

```
src/agent/
  analyst.py     Analyst：模式分发（pipeline vs agent）
  pipeline.py    pipeline 模式：确定性编排（意图解析+抓取+摘要+校验+记忆）
  agent_loop.py  agent 模式：LLM 自主工具调用循环 + 循环内 verify 反馈
  extractor.py   确定性抓取（两种模式共用，正确性核心）
  verifier.py    校验：编造 + 归属错，物理删除无来源数字
  edgar.py       SEC EDGAR 客户端（限速、缓存、拼 filing URL）
  schema.py      Provenance / Fact / QueryIntent / Answer
  metrics.py     指标 → XBRL tag 同义映射
  skills.py      分析师配方（内置 + 用户 YAML）
  profile.py     用户偏好记忆（3 个 JSON）
  table.py       终端表格 + Excel/CSV 导出（超链接 + provenance sheet）
  llm.py         LLM 多 provider 抽象（anthropic/openai/deepseek）
  cli.py         命令行入口
eval/            评测：题目、oracle、运行器、指标
tests/           64 个测试
```

## 已知限制

- **财年 Q4 跨自然年**：财年横跨 12 月 31 日的公司（NVDA 财年 1 月底结束），SEC 有时不提供单独的 Q4 期间型 fact；provenance 的起止日期始终可消歧。
- **跨公司季度不对齐**：不同公司财年结束月不同，对比表按各自精确日期分列，不强行对齐。
- **公司不披露某 tag**：如 AMD 不单独披露 `Liabilities`（只有 `LiabilitiesAndStockholdersEquity`），harness 返回"无数据"而非用错数。
- **确定性 ticker 解析**：过滤常见英文/金融词，单字符 ticker（"V"）或与金融词重合的 ticker（"CASH"/"NET"）需用全名或加入 watchlist。
- **归属校验是行粒度**：一行内多个公司多个数字的对调分辨不出；要更细需拆到从句级。
