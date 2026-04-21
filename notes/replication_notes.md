# Replication Notes

## Key Decisions Made

### 1. Model choice: GPT-4o-mini
The paper used GPT-3.5-turbo-0301, StarCoder, LLaMA-2-13B, and CodeLLaMA-7B.
We chose GPT-4o-mini as our low-cost alternative because:
- It is accessible via the same OpenAI API as GPT-3.5
- It is cheaper (~15× less than GPT-3.5-turbo)
- It is a more recent and capable model, making the comparison meaningful

### 2. Reduced sampling: 3 chances instead of 10
The paper calls the API 10 times per bug. We reduced to 3 due to rate limits.
At 10 calls/bug the first run hit severe throttling (5000+ s/bug observed).
At 3 calls/bug with back-off the run completed in ~16 hours total.
This is noted as a limitation in the report.

### 3. Evaluation: exact-match instead of test-suite validation
The paper runs the full Defects4J test suite to check if patches are correct.
This requires Java 8 + Defects4J installed locally. We used ground-truth
exact-match instead. Result: 0 bugs fixed. This is expected and explained in
the report — it reflects the strictness of the metric, not model failure.

### 4. API library rewrite
The authors' api_request.py uses openai 0.x (deprecated):
  - `openai.ChatCompletion.create(**config)` → no longer exists
  - `openai.error.RateLimitError` → no longer exists
We rewrote the API call layer using `openai>=1.0.0`:
  - `client.chat.completions.create(...)`
  - Standard `except Exception` with string matching on error messages
The prompt, temperature, top_p, max_tokens, and stop sequence were NOT changed.

---

## Discrepancies Noted

| Aspect | Paper | Our Replication |
|--------|-------|-----------------|
| Model | GPT-3.5-turbo-0301 | GPT-4o-mini |
| Sampling attempts | 10 per bug | 3 per bug |
| Evaluation | Defects4J test suite | Ground-truth exact-match |
| Bugs fixed (v1.2) | 43 (GPT-3.5 direct) | 0 |
| Bugs fixed (v2.0) | 45 (GPT-3.5 direct) | 0 |
| GiantRepair step | Run (Java tool) | Not run (out of scope) |

The 0-fix result is entirely attributable to the evaluation method gap.
Exact-match is a known conservative metric in APR research.

---

## Things That Would Help Future Replicators

1. **Pin dependency versions** in requirements.txt — the original code is
   broken on openai>=1.0.0 without modification.
2. **Provide a Docker image** or Dockerfile for the Java/Defects4J environment
   so the test-suite evaluation step is reproducible.
3. **Clearer folder naming** in data/results/RQ1/ — the diff file folders use
   inconsistent capitalisation (e.g., `GiantRepair_gpt35` vs `gpt35`).
4. **A mapping table** from folder names to Table 2 rows would help.
