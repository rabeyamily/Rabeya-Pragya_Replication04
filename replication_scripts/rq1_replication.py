"""
RQ1 Replication — GPT-4o-mini on Defects4J
===========================================

Usage
-----
# Step 1 — generate patches (run twice: once for v12, once for v20)
python rq1_replication.py generate --version v12          # D4J v1.2, 267 bugs
python rq1_replication.py generate --version v20          # D4J v2.0, 216 bugs

# Quick smoke-test (3 bugs only, 2 API calls each — costs < $0.01)
python rq1_replication.py generate --version v12 --limit 3 --chances 2

# Step 2 — evaluate patches against ground-truth developer fixes
python rq1_replication.py evaluate

# Step 3 — print Table 2
python rq1_replication.py table
python rq1_replication.py table --rq1_dir ../GiantRepair/data/results/RQ1

# Run all three steps back-to-back (v12 + v20 generate → evaluate → table)
python rq1_replication.py all
"""

import os, sys, re, json, time, argparse
from pathlib import Path
from difflib import unified_diff
from dotenv import load_dotenv
from tqdm import tqdm
from openai import OpenAI

# ── imports from the four files copied from the paper ─────────────────────────
from prompt    import JAVA_LONG_VARY_PROMPT
from parse_d4j import pick_smallest_example_fix

# load .env from this folder or its parent
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
load_dotenv()  # also try cwd, just in case

# ── constants ─────────────────────────────────────────────────────────────────
D4J_V12   = {"Chart", "Closure", "Lang", "Math", "Time", "Mockito"}
D4J_V20   = {"Cli", "Codec", "Collections", "Compress", "Csv", "Gson",
              "JacksonCore", "JacksonDatabind", "JacksonXml", "Jsoup", "JxPath"}
STOP_SEQ  = "// Provide a fix for the buggy function"

# paper numbers
PAPER = {
    "GPT-3.5-turbo": {"v12_direct":43,"v12_gr":10,"v12_total":53,
                      "v20_direct":45,"v20_gr": 8,"v20_total":53},
    "StarCoder":      {"v12_direct":42,"v12_gr":13,"v12_total":55,
                      "v20_direct":44,"v20_gr":10,"v20_total":54},
    "LLaMA-2-13B":    {"v12_direct":19,"v12_gr": 6,"v12_total":25,
                      "v20_direct":18,"v20_gr": 6,"v20_total":24},
    "CodeLLaMA-7B":   {"v12_direct":39,"v12_gr":11,"v12_total":50,
                      "v20_direct":34,"v20_gr": 9,"v20_total":43},
}

# ═══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════════════════

def load_dataset(path: str = "single_function_repair.json") -> dict:
    """
    Load single_function_repair.json.
    Returns {  'Project-ID.java': {'buggy': ..., 'fix': ...}  }
    Keys carry the .java suffix that pick_smallest_example_fix expects.
    Leading indentation is stripped from both fields (mirrors parse_d4j.py).
    """
    with open(path) as f:
        raw = json.load(f)
    out = {}
    for bug_id, entry in raw.items():
        for field in ("buggy", "fix"):
            lines = entry[field].splitlines()
            if not lines:
                continue
            indent = len(lines[0]) - len(lines[0].lstrip())
            entry[field] = "\n".join(line[indent:] for line in lines)
        out[bug_id + ".java"] = {"buggy": entry["buggy"], "fix": entry["fix"]}
    return out


def normalise(code: str) -> str:
    """Strip + collapse whitespace per line, drop blanks, lower-case."""
    lines = [re.sub(r"\s+", " ", l.strip()).lower() for l in code.splitlines()]
    return "\n".join(l for l in lines if l)


def get_diff(a: str, b: str) -> str:
    return "".join(ln + "\n" for ln in unified_diff(a.split("\n"), b.split("\n"), lineterm=""))


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — generate patches
# ═══════════════════════════════════════════════════════════════════════════════

def _call_model(client: OpenAI, prompt: str, max_tokens: int = 3000) -> str | None:
    """One API call to gpt-4o-mini.  Retries on rate-limit; returns None if skippable."""
    while True:
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.8,
                top_p=0.95,
                stop=STOP_SEQ,
            )
            choice = resp.choices[0]
            return choice.message.content.strip() if choice.finish_reason == "stop" else None
        except Exception as e:
            msg = str(e)
            if any(x in msg.lower() for x in ("reduce", "context_length", "maximum context")):
                max_tokens -= 200
                if max_tokens < 100:
                    return None
            elif "rate" in msg.lower() or "429" in msg:
                print("\n    [RATE LIMIT] waiting 60 s …")
                time.sleep(60)
            else:
                print(f"\n    [ERROR] {msg[:120]} — retrying in 5 s")
                time.sleep(5)


def _process_one_bug(client, file_key, bug, dataset, patch_dir, chances):
    out_path = Path(patch_dir) / file_key.replace(".java", ".json")
    if out_path.exists():
        return None                         # already done — resumable

    try:
        ex_bug, ex_fix = pick_smallest_example_fix(dataset, file_key, only_same=True)
    except (IndexError, KeyError):
        ex_bug, ex_fix = pick_smallest_example_fix(dataset, file_key, only_same=False)

    prompt = JAVA_LONG_VARY_PROMPT.format(example_bug=ex_bug, example_fix=ex_fix, bug=bug["buggy"])

    patches, seen = [], {}
    for _ in range(chances):
        output = _call_model(client, prompt)
        if output is None:
            continue
        diff = get_diff(bug["buggy"], output)
        if diff in seen:
            patches[seen[diff]]["num"] += 1
        else:
            seen[diff] = len(patches)
            patches.append({"output": output, "diff": diff, "num": 1})

    with open(out_path, "w") as f:
        json.dump(patches, f, indent=2)
    return len(patches)


def cmd_generate(args):
    api_key = os.getenv("OpenAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        sys.exit("ERROR: OpenAI_API_KEY not found in .env")
    client = OpenAI(api_key=api_key)

    dataset    = load_dataset(args.dataset)
    target     = D4J_V12 if args.version == "v12" else D4J_V20 if args.version == "v20" else D4J_V12 | D4J_V20
    bugs       = {k: v for k, v in dataset.items() if k.split("-")[0] in target}
    patch_dir  = Path(args.patch_dir)
    patch_dir.mkdir(parents=True, exist_ok=True)

    if args.limit:
        bugs = dict(list(bugs.items())[: args.limit])

    already = sum(1 for k in bugs if (patch_dir / k.replace(".java", ".json")).exists())
    print(f"\nGenerating patches with gpt-4o-mini")
    print(f"  version={args.version}  bugs={len(bugs)}  chances={args.chances}  already_done={already}")
    print(f"  output → {patch_dir}/\n")

    for file_key, bug in tqdm(bugs.items(), desc="Bugs"):
        n = _process_one_bug(client, file_key, bug, dataset, patch_dir, args.chances)
        if n is not None:
            tqdm.write(f"  {file_key}: {n} unique patches")

    print(f"\nDone. Run:  python {Path(__file__).name} evaluate")


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — evaluate
# ═══════════════════════════════════════════════════════════════════════════════

def _evaluate_set(patch_dir: Path, dataset: dict, projects: set) -> dict:
    fixed, not_fixed, no_output, missing = [], [], [], []
    details = {}

    for file_key in sorted(dataset):
        if file_key.split("-")[0] not in projects:
            continue
        bug_id   = file_key.replace(".java", "")
        out_file = patch_dir / file_key.replace(".java", ".json")

        if not out_file.exists():
            missing.append(bug_id)
            details[bug_id] = {"fixed": False, "status": "missing"}
            continue
        with open(out_file) as f:
            candidates = json.load(f)
        if not candidates:
            no_output.append(bug_id)
            details[bug_id] = {"fixed": False, "status": "no_output"}
            continue

        gt    = normalise(dataset[file_key]["fix"])
        found = any(normalise(c["output"]) == gt for c in candidates)
        status = "fixed" if found else "not_fixed"
        (fixed if found else not_fixed).append(bug_id)
        details[bug_id] = {"fixed": found, "status": status, "n_unique": len(candidates)}

    return {"fixed": sorted(fixed), "not_fixed": sorted(not_fixed),
            "no_output": sorted(no_output), "missing": sorted(missing),
            "details": details}


def _print_project_breakdown(result: dict) -> None:
    per = {}
    for bug_id, info in result["details"].items():
        proj = bug_id.split("-")[0]
        per.setdefault(proj, {"fixed": 0, "total": 0})
        per[proj]["total"] += 1
        if info["fixed"]:
            per[proj]["fixed"] += 1
    print(f"\n  {'Project':<20} {'Fixed':>6} {'Total':>7}")
    print(f"  {'-'*35}")
    gf = gt = 0
    for proj in sorted(per):
        f, t = per[proj]["fixed"], per[proj]["total"]
        gf += f; gt += t
        print(f"  {proj:<20} {f:>6} {t:>7}")
    print(f"  {'-'*35}")
    print(f"  {'TOTAL':<20} {gf:>6} {gt:>7}")


def cmd_evaluate(args):
    out_dir   = Path(args.out_dir);  out_dir.mkdir(parents=True, exist_ok=True)
    patch_dir = Path(args.patch_dir)
    dataset   = load_dataset(args.dataset)

    for label, projects in [("v12", D4J_V12), ("v20", D4J_V20)]:
        print(f"\n{'='*55}\n  Defects4J {label.upper()} evaluation\n{'='*55}")
        result = _evaluate_set(patch_dir, dataset, projects)
        print(f"  Fixed       : {len(result['fixed'])}")
        print(f"  Not fixed   : {len(result['not_fixed'])}")
        print(f"  No output   : {len(result['no_output'])}")
        print(f"  File missing: {len(result['missing'])}")
        _print_project_breakdown(result)
        path = out_dir / f"evaluation_{label}.json"
        with open(path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\n  Saved → {path}")

    v12 = json.load(open(out_dir / "evaluation_v12.json"))
    v20 = json.load(open(out_dir / "evaluation_v20.json"))
    summary = {"model": "gpt-4o-mini",
               "evaluation": "ground_truth_exact_match",
               "d4j_v12": {"fixed": len(v12["fixed"]), "fixed_ids": v12["fixed"]},
               "d4j_v20": {"fixed": len(v20["fixed"]), "fixed_ids": v20["fixed"]}}
    with open(out_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary → {out_dir}/summary.json")
    print(f"Run:  python {Path(__file__).name} table")


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Table 2
# ═══════════════════════════════════════════════════════════════════════════════

def _recount_from_diffs(rq1_dir: str) -> None:
    mapping = {"GPT-3.5-turbo": ("gpt35","GiantRepair_gpt35"),
               "StarCoder":     ("starcoder","GiantRepair_starcoder"),
               "LLaMA-2-13B":   ("llama","GiantRepair_llama"),
               "CodeLLaMA-7B":  ("codellama","GiantRepair_codellama")}
    for model, (d, gr) in mapping.items():
        for ver, vdir in (("v12","Defects4J_v12"), ("v20","Defects4J_v20")):
            dp  = Path(rq1_dir) / vdir / d
            grp = Path(rq1_dir) / vdir / gr
            dc  = len(list(dp.glob("*.diff")))  if dp.is_dir()  else PAPER[model][f"{ver}_direct"]
            grc = len(list(grp.glob("*.diff"))) if grp.is_dir() else PAPER[model][f"{ver}_gr"]
            PAPER[model][f"{ver}_direct"] = dc
            PAPER[model][f"{ver}_gr"]     = grc
            PAPER[model][f"{ver}_total"]  = dc + grc


def _fmt(v) -> str:
    return str(v) if v is not None else "—"


def _print_full_table(our_v12, our_v20) -> None:
    W = [22, 17, 14, 15, 17, 14, 15]
    SEP = "  " + "-" * (sum(W) + len(W) * 2)

    def row(cols):
        parts = [f"{str(cols[0]):<{W[0]}}"] + [f"{str(v):>{W[i+1]}}" for i, v in enumerate(cols[1:])]
        print("  " + "  ".join(parts))

    print(); print("=" * (sum(W) + len(W) * 2 + 4))
    print("  TABLE 2 — Bugs Correctly Fixed on Defects4J")
    print("=" * (sum(W) + len(W) * 2 + 4))
    row(["Model","v1.2 Direct","v1.2 +GR","v1.2 Total","v2.0 Direct","v2.0 +GR","v2.0 Total"])
    print(SEP)
    for model, r in PAPER.items():
        row([model, r["v12_direct"], r["v12_gr"], r["v12_total"],
                    r["v20_direct"], r["v20_gr"], r["v20_total"]])
    print(SEP)
    row(["GPT-4o-mini (ours)", _fmt(our_v12), "N/A", "N/A", _fmt(our_v20), "N/A", "N/A"])
    print(SEP)
    print("\n  +GR = additional bugs fixed only with GiantRepair on top of the LLM.")
    print("  N/A = GiantRepair step not run (requires Java + Defects4J).")
    print("  Our evaluation uses ground-truth exact-match, not test-suite validation.")


def _print_comparison_table(our_v12, our_v20) -> None:
    print(); print("=" * 65)
    print("  COMPARISON — Direct LLM Only  (GPT-4o-mini vs. paper models)")
    print("=" * 65)
    print(f"  {'Model':<22}  {'D4J v1.2':>10}  {'D4J v2.0':>10}  {'Combined':>10}")
    print("  " + "-" * 58)
    for model, r in PAPER.items():
        v12, v20 = r["v12_direct"], r["v20_direct"]
        print(f"  {model:<22}  {v12:>10}  {v20:>10}  {v12+v20:>10}")
    print("  " + "-" * 58)
    v12s = _fmt(our_v12); v20s = _fmt(our_v20)
    comb = _fmt((our_v12 or 0) + (our_v20 or 0)) if our_v12 is not None or our_v20 is not None else "—"
    print(f"  {'GPT-4o-mini (ours)':<22}  {v12s:>10}  {v20s:>10}  {comb:>10}")
    print("  " + "-" * 58)


def cmd_table(args):
    if args.rq1_dir and os.path.isdir(args.rq1_dir):
        print(f"Re-counting diff files in {args.rq1_dir} …")
        _recount_from_diffs(args.rq1_dir)

    our_v12 = our_v20 = None
    summary_path = Path(args.out_dir) / "summary.json"
    if summary_path.exists():
        s = json.load(open(summary_path))
        our_v12 = s["d4j_v12"]["fixed"]
        our_v20 = s["d4j_v20"]["fixed"]
    else:
        print(f"[WARNING] {summary_path} not found — run 'evaluate' first.\n")

    _print_full_table(our_v12, our_v20)
    _print_comparison_table(our_v12, our_v20)

    out_path = Path(args.out_dir) / "table2.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"paper": PAPER, "gpt4o_mini":
                   {"d4j_v12_direct": our_v12, "d4j_v20_direct": our_v20}}, f, indent=2)
    print(f"\nTable saved → {out_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description="RQ1 replication: GPT-4o-mini on Defects4J",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--dataset",    default="../datasets/single_function_repair.json")
    p.add_argument("--patch_dir",  default="../outputs/patches")
    p.add_argument("--out_dir",    default="../outputs")

    sub = p.add_subparsers(dest="cmd", required=True)

    # generate
    g = sub.add_parser("generate", help="Step 3 — call gpt-4o-mini to generate patches")
    g.add_argument("--version",  choices=["v12","v20","all"], default="all")
    g.add_argument("--chances",  type=int, default=10, help="API calls per bug (paper used 10)")
    g.add_argument("--limit",    type=int, default=None, help="Process only first N bugs (smoke test)")

    # evaluate
    sub.add_parser("evaluate", help="Step 4 — compare patches to ground-truth developer fixes")

    # table
    t = sub.add_parser("table", help="Step 5 — print Table 2")
    t.add_argument("--rq1_dir", default=None,
                   help="Path to GiantRepair/data/results/RQ1 (for live diff-file counts)")

    # all
    a = sub.add_parser("all", help="Run all steps: generate (v12+v20) → evaluate → table")
    a.add_argument("--chances",  type=int, default=10)
    a.add_argument("--rq1_dir",  default=None)

    args = p.parse_args()

    if args.cmd == "generate":
        cmd_generate(args)
    elif args.cmd == "evaluate":
        cmd_evaluate(args)
    elif args.cmd == "table":
        cmd_table(args)
    elif args.cmd == "all":
        for ver in ("v12", "v20"):
            args.version = ver
            args.limit   = None
            cmd_generate(args)
        cmd_evaluate(args)
        cmd_table(args)


if __name__ == "__main__":
    main()
