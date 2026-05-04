# MCP Server Evaluation Guide

## Overview

Create comprehensive evaluations to test whether LLMs can effectively use your MCP server to answer realistic, complex questions using only the tools provided.

---

## Quick Reference

### Evaluation Requirements
- Create 10 human-readable questions
- Questions must be READ-ONLY, INDEPENDENT, NON-DESTRUCTIVE
- Each question requires multiple tool calls (potentially dozens)
- Answers must be single, verifiable values
- Answers must be STABLE (won't change over time)

### Output Format
```xml
<evaluation>
   <qa_pair>
      <question>Your question here</question>
      <answer>Single verifiable answer</answer>
   </qa_pair>
</evaluation>
```

---

## Purpose

The measure of quality of an MCP server is NOT how well or comprehensively the server implements tools, but how well these implementations enable LLMs with no other context and access ONLY to the MCP servers to answer realistic and difficult questions.

## Question Guidelines

### Core Requirements

1. **Questions MUST be independent** — no dependency on other questions
2. **Questions MUST require ONLY NON-DESTRUCTIVE AND IDEMPOTENT tool use**
3. **Questions must be REALISTIC, CLEAR, CONCISE, and COMPLEX** — requiring multiple (potentially dozens of) tools or steps

### Complexity and Depth

4. **Require deep exploration** — multi-hop questions requiring sequential tool calls
5. **May require extensive paging** — querying old data, niche information
6. **Require deep understanding** — not surface-level knowledge
7. **Not solvable with straightforward keyword search** — use synonyms, paraphrases

### Tool Testing

8. **Stress-test tool return values** — large JSON, multiple data modalities (IDs, timestamps, URLs)
9. **Reflect real human use cases**
10. **May require dozens of tool calls**
11. **Include ambiguous questions** — but with a SINGLE VERIFIABLE ANSWER

### Stability

12. **Answer DOES NOT CHANGE** — no "current state" questions (don't count reactions, replies, members)
13. **Create challenging questions** — some may not be solvable with available tools

## Answer Guidelines

1. **Verifiable via direct string comparison** — specify format in question (YYYY/MM/DD, True/False, A/B/C/D)
2. **Prefer HUMAN-READABLE formats** — names, datetimes, URLs, yes/no
3. **STABLE/STATIONARY** — based on "closed" concepts, historical data
4. **CLEAR and UNAMBIGUOUS** — single, clear answer
5. **DIVERSE** — user IDs, names, timestamps, channel names, etc.
6. **NOT complex structures** — not lists, not objects, single verifiable values

## Evaluation Process

### Step 1: Documentation Inspection
Read API documentation, understand endpoints and functionality.

### Step 2: Tool Inspection
List available tools, understand schemas and descriptions WITHOUT calling them.

### Step 3: Developing Understanding
Iterate until you understand the kinds of tasks to create. Do NOT read MCP server code.

### Step 4: Read-Only Content Inspection
Use tools with READ-ONLY operations to identify specific content for questions. Use `limit` parameter (<10), use pagination. Make INCREMENTAL, SMALL, AND TARGETED tool calls.

### Step 5: Task Generation
Create 10 questions following all guidelines above.

## Example Good Questions

```xml
<qa_pair>
   <question>Find the repository that was archived in Q3 2023 and had previously been the most forked project in the organization. What was the primary programming language used?</question>
   <answer>Python</answer>
</qa_pair>

<qa_pair>
   <question>Among all bugs reported in January 2024 that were marked as critical priority, which assignee resolved the highest percentage within 48 hours? Provide the username.</question>
   <answer>alex_eng</answer>
</qa_pair>
```

## Example Poor Questions

- "How many open issues are currently assigned?" — answer changes over time
- "Find the PR with title 'Add authentication feature'" — too easy, keyword search
- "List all repositories with Python" — answer is a list, hard to verify

## Running Evaluations

### Setup

```bash
pip install anthropic mcp
export ANTHROPIC_API_KEY=your_api_key_here
```

### Running

```bash
# Local STDIO Server
python scripts/evaluation.py \
  -t stdio \
  -c python \
  -a my_mcp_server.py \
  evaluation.xml

# HTTP Server
python scripts/evaluation.py \
  -t http \
  -u https://example.com/mcp \
  -H "Authorization: Bearer token123" \
  evaluation.xml
```

### Output

The report includes:
- Accuracy (correct/total)
- Average task duration and tool calls
- Per-task results with agent feedback
