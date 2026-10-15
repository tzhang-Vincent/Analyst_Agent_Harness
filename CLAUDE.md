## Coding Task

We're designing a financial research agent, for financial analysts to query and analyze public financial documents. An LLM can help them find and cross reference many financial documents. However, they're very concerned about making financial decisions based on data that might have hallucinations, so they want clear provenance tracking for generated data.

Design and implement an agentic harness for GPT that outperforms ChatGPT on the following task:
- Analysts typically specialize in a specific sector. You may restrict your attention to a specific sector or set of companies. You might consider how the agent will adapt to the user over time.
- Analysts should be able to prompt the agent to return and summarize public financial statements from some set of companies.
- Analysts should be able to generate a table or spreadsheet comparing financial data across quarters, with clear provenance information so they can double check the generated output against the original data source.

We'll ask about the design, implementation, and evaluation of the harness, and which features are key to the performance.

## Submission

When you're done, push your code to a GitHub repository and email the link to recruiting@persephone-intelligence.com by the night before your interview.
- If the repository is private, please grant us access before sending the link.
- Include a README explaining how to set up and run the harness, and briefly summarize your design decisions and how you evaluated it.

---

## 任务（中文翻译）

我们要设计一个金融研究 agent，供金融分析师查询和分析公开金融文档。LLM 能帮他们查找和交叉引用大量金融文档，但他们非常担心基于可能有幻觉的数据做金融决策，因此需要为生成的数据提供清晰的溯源（provenance）追踪。

设计并实现一个针对 GPT 的 agentic harness，使其在以下任务上优于 ChatGPT：
- 分析师通常专精于某个特定行业。你可以把注意力限定在某个行业或一组公司上；也可以考虑 agent 如何随时间适应用户。
- 分析师应能提示 agent 返回并总结某组公司的公开财务报表。
- 分析师应能生成跨季度比较财务数据的表格/电子表格，并带有清晰的溯源信息，以便把生成结果与原始数据源逐条核对。

我们会就 harness 的设计、实现和评测提问，以及哪些特性对性能起关键作用。

## 提交要求（中文翻译）

完成后，把代码推送到 GitHub 仓库，并在面试前一晚之前把链接发邮件到 recruiting@persephone-intelligence.com。
- 如果仓库是私有的，请在发送链接前授予我们访问权限。
- 附上 README，说明如何搭建和运行 harness，并简要总结你的设计决策以及如何评测。
