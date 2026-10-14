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
