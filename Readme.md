# Replication Study: GiantRepair

- **Paper Title**: Hybrid Automated Program Repair by Combining Large Language Models and Program Analysis
- **Authors**: Fengjie Li, Jiajun Jiang, Jiajun Sun, and Hongyu Zhang
- **Replication Team**: Rabeya Zahan Mily & Pragya Chapagain
- **Course**: CS-UH 3260 Software Analytics, NYUAD
- **Brief Description**:
  - The original paper introduces GiantRepair, a hybrid Automated Program Repair (APR) approach that first generates patch candidates using LLMs (GPT-3.5-turbo, StarCoder, LLaMA-2-13B, CodeLLaMA-7B), then constructs patch skeletons from those candidates and instantiates them with context-aware program analysis to improve correctness. The method is evaluated on Defects4J v1.2 (267 bugs) and v2.0 (216 bugs) under both perfect and automated fault localization settings.
  - This replication study firstly focuses on RQ1: replicating the direct LLM patch-generation step (Steps 3–5 of the pipeline) using GPT-4o-mini as a newer, more cost-efficient model. We use the same `single_function_repair.json` dataset and few-shot prompt from the original paper, generate 10 patch candidates per bug, evaluate using ground-truth exact-match comparison, and report results in the same Table 2 format alongside the paper's original numbers.

  - The second part of this replication focuses on manual patch analysis. 
  Ten patches were randomly selected from the GiantRepair artifact across 
  multiple model folders (GiantRepair_gpt35, GiantRepair_starcoder, 
  GiantRepair_codellama). For each patch, the generated fix was compared 
  against the original buggy method to evaluate correctness, cleanliness, 
  and whether the root cause was addressed.
---

## Repository Structure

```
.
├── README.md                        ← this file
├── datasets/
│   └── single_function_repair.json  ← Defects4J bug dataset (483 bugs)
├── replication_scripts/
│   ├── rq1_replication.py           ← main replication script
│   ├── requirements.txt             ← Python dependencies
│   ├── prompt.py                    ← 2-shot prompt template (from artifact)
│   ├── parse_d4j.py                 ← dataset parsing helper (from artifact)
│   └── api_request.py               ← original API wrapper (unused; kept for reference)
├── outputs/
│   ├── patches/                     ← 483 JSON files, one per bug
│   ├── evaluation_v12.json          ← per-bug evaluation results, D4J v1.2
│   ├── evaluation_v20.json          ← per-bug evaluation results, D4J v2.0
│   ├── summary.json                 ← aggregated fix counts
│   └── table2.json                  ← Table 2 data
├── logs/
│   └── run_log.md                   ← run timeline, errors encountered, timings
└── notes/
    └── replication_notes.md         ← methodological decisions and discrepancies
```

---

## Dataset

`datasets/single_function_repair.json` is taken directly from the authors'
artifact (`d4j-info/single_function_repair.json`).

It contains **483 single-function Defects4J bugs**:
- **267 bugs** from Defects4J v1.2 (Chart, Closure, Lang, Math, Mockito, Time)
- **216 bugs** from Defects4J v2.0 (Cli, Codec, Collections, Compress, Csv,
  Gson, JacksonCore, JacksonDatabind, JacksonXml, Jsoup, JxPath)

Each entry contains the buggy method, the ground-truth fix, and project
metadata.

---

## Replication Scripts

All scripts live in `replication_scripts/`. Run them from that directory.

### Setup

```bash
cd replication_scripts
python3 -m venv ../.venv          # create a virtual environment (once)
source ../.venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file at the repository root containing your OpenAI key:

```
OpenAI_API_KEY=sk-...
```

### Running the full pipeline

```bash
# From inside replication_scripts/
python3 rq1_replication.py all --chances 3
```

This runs the four steps sequentially:
1. **generate (v1.2)** — calls GPT-4o-mini for each D4J v1.2 bug
2. **generate (v2.0)** — calls GPT-4o-mini for each D4J v2.0 bug
3. **evaluate** — compares generated patches to ground truth
4. **table** — prints Table 2 and writes `outputs/table2.json`

If interrupted, it resumes automatically (already-done bugs are skipped).

### Running individual steps

```bash
# Generate patches for v1.2 only
python3 rq1_replication.py generate --version v12 --chances 3

# Generate patches for v2.0 only
python3 rq1_replication.py generate --version v20 --chances 3

# Evaluate generated patches
python3 rq1_replication.py evaluate

# Print Table 2
python3 rq1_replication.py table
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--chances N` | 10 | Number of patches to generate per bug |
| `--dataset PATH` | `../datasets/single_function_repair.json` | Dataset file |
| `--patch_dir PATH` | `../outputs/patches` | Where to save patch JSON files |
| `--out_dir PATH` | `../outputs` | Where to save evaluation output |

### Key implementation differences from the original artifact

| Aspect | Original paper | This replication |
|--------|----------------|------------------|
| Model | GPT-3.5-turbo-0301 | **GPT-4o-mini** |
| Sampling attempts | 10 per bug | 3 per bug (rate limit mitigation) |
| OpenAI client | `openai 0.x` (deprecated) | `openai >= 1.0.0` |
| Evaluation | Defects4J test-suite | **Ground-truth exact-match** |
| Rate-limit handling | Flat 60 s wait | Exponential back-off (15→120 s) |

---

## Outputs

All generated results are in `outputs/`.

- `patches/<bug_id>.json` — raw model outputs for each bug
- `evaluation_v12.json` — `{bug_id: {fixed: bool, ...}}` for each v1.2 bug
- `evaluation_v20.json` — same for v2.0
- `summary.json` — overall counts
- `table2.json` — Table 2 values used in the report

### Results summary

| Benchmark | Bugs | Fixed (exact-match) | Fixed (paper, GPT-3.5 raw) |
|-----------|------|---------------------|----------------------------|
| D4J v1.2  | 267  | 0                   | 43                         |
| D4J v2.0  | 216  | 0                   | 45                         |

The 0-fix result is expected. Exact-match is a known conservative metric;
the paper uses test-suite validation which accepts any semantically equivalent
fix. See `notes/replication_notes.md` for a full explanation.

---

## Logs

`logs/run_log.md` documents:
- Two runs (one failed due to rate limits, one successful)
- Total wall-clock time: **~17 hours**
- API call count: ~1,449 (483 bugs × 3 chances)
- Per-project timing and anomalies

---

## Notes

`notes/replication_notes.md` records:
- Rationale for each methodological choice
- Full discrepancy table between paper and replication
- Suggestions for future replicators

### GenAI Usage

**GenAI Usage**: Took help from claude to understand the paper artifact repository's structure and code and debugging.
  - **How it was used**:
    - Understanding the original paper's pipeline and mapping it to implementation steps
    - Exploring the `single_function_repair.json` dataset structure and understanding the data fields (`buggy`, `fix`, bug IDs)
    - Debugging the main replication script (`rq1_replication.py`)
    - Debugging OpenAI API integration (rate limit handling, token limits, response parsing)
    - Also used to understand the initial bugs when doing manual patch analysis 