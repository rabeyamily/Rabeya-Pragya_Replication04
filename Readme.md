### 1. Project Title and Overview

- **Paper Title**: Hybrid Automated Program Repair by Combining Large Language Models and Program Analysis
- **Authors**: Fengjie Li, Jiajun Jiang, Jiajun Sun, and Hongyu Zhang
- **Replication Team**: Rabeya Zahan Mily & Pragya Chapagain
- **Course**: CS-UH 3260 Software Analytics, NYUAD
- **Brief Description**:
  - The original paper introduces GiantRepair, a hybrid Automated Program Repair (APR) approach that first generates patch candidates using LLMs (GPT-3.5-turbo, StarCoder, LLaMA-2-13B, CodeLLaMA-7B), then constructs patch skeletons from those candidates and instantiates them with context-aware program analysis to improve correctness. The method is evaluated on Defects4J v1.2 (267 bugs) and v2.0 (216 bugs) under both perfect and automated fault localization settings.
  - This replication study firstly focuses on RQ1: replicating the direct LLM patch-generation step (Steps 3–5 of the pipeline) using GPT-4o-mini as a newer, more cost-efficient model. We use the same `single_function_repair.json` dataset and few-shot prompt from the original paper, generate 10 patch candidates per bug, evaluate using ground-truth exact-match comparison, and report results in the same Table 2 format alongside the paper's original numbers.

  - Pragya's part

### 2. Repository Structure

```
Readme.md                          # This file — documentation for the repository
.env                               # API key configuration (not committed)
RQ1-Replication/
  rq1_replication.py               # Main replication script (generate, evaluate, table)
  prompt.py                        # Few-shot prompt template (JAVA_LONG_VARY_PROMPT) from the paper
  parse_d4j.py                     # Helper to pick the smallest in-project example fix
  api_request.py                   # Low-level OpenAI API wrapper
  single_function_repair.json      # Dataset: 483 bugs (D4J v1.2 + v2.0) with buggy/fix pairs
  requirements.txt                 # Python dependencies
  results/
    patches/                       # Generated patch JSON files — one per bug (output of `generate`)
    evaluation_v12.json            # Per-bug evaluation results for Defects4J v1.2
    evaluation_v20.json            # Per-bug evaluation results for Defects4J v2.0
    summary.json                   # Aggregated fix counts for both versions
    table2.json                    # Full Table 2 data (paper models + our GPT-4o-mini results)
```

### 3. Setup Instructions

- **Prerequisites**:
  - OS: macOS, Linux, or Windows (tested on macOS 15)
  - Python 3.10 or higher
  - An OpenAI API key with access to `gpt-4o-mini`
  - Required Python packages (see `RQ1-Replication/requirements.txt`):
    - `openai >= 1.0.0`
    - `python-dotenv >= 1.0.0`
    - `tqdm >= 4.65.0`

- **Installation Steps**:
  For RQ 1:
  1. Clone this repository and navigate to the project folder:
     ```bash
     cd Rabeya-Pragya_Replication04
     ```
  2. Install dependencies:
     ```bash
     pip install -r RQ1-Replication/requirements.txt
     ```
  3. Create a `.env` file in the project root and add your OpenAI API key:
     ```
     OpenAI_API_KEY=sk-...
     ```
  4. Run the replication from the `RQ1-Replication/` directory:
     ```bash
     cd RQ1-Replication

     # Generate patches for Defects4J v1.2 and v2.0 (10 chances per bug)
     python rq1_replication.py generate --version v12
     python rq1_replication.py generate --version v20

     # Evaluate patches against ground-truth developer fixes
     python rq1_replication.py evaluate

     # Print Table 2
     python rq1_replication.py table
     ```
  5. For a quick test (3 bugs, 2 API calls each):
     ```bash
     python rq1_replication.py generate --version v12 --limit 3 --chances 2
     ```

### 4. GenAI Usage

**GenAI Usage**: Took help from claude to understand the paper artifact repository's structure and code and debugging.
  - **How it was used**:
    - Understanding the original paper's pipeline and mapping it to implementation steps
    - Exploring the `single_function_repair.json` dataset structure and understanding the data fields (`buggy`, `fix`, bug IDs)
    - Debugging the main replication script (`rq1_replication.py`)
    - Debugging OpenAI API integration (rate limit handling, token limits, response parsing)
