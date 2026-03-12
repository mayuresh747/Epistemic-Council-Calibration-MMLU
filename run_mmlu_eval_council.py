#!/usr/bin/env python3
"""
Epistemic Council MMLU Evaluation Script

Runs each MMLU question through a 4-phase debate between 5 epistemic models,
then uses M1-Council-Orchestrator to reach a final consensus answer.

Phases:
  1. Independent Opening  — 5 models answer in parallel (blind, no cross-talk)
  2. Critique Round 1     — 5 models see Phase 1 transcript, critique & revise
  3. Critique Round 2     — 5 models see Phase 1+2 transcript, final position
  4. Consensus Resolution — majority vote; orchestrator only if no majority

Usage:
    python3 run_mmlu_eval_council.py              # All 100 questions
    python3 run_mmlu_eval_council.py --limit 5    # First 5 only
    python3 run_mmlu_eval_council.py --resume     # Resume from previous run
"""

import csv
import re
import time
import argparse
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import requests

# ─── Configuration ────────────────────────────────────────────────────────────
API_URL    = "http://localhost:8001/v1/messages"
MAX_RETRIES  = 3
RETRY_DELAY  = 10  # seconds between retries
INTER_MODEL_DELAY = 2  # seconds between sequential model calls within a phase

AGENTS = ["Rationalist", "Empiricist", "Coherentist", "Pragmatist", "Standpoint"]
AGENT_MODELS = {
    "Rationalist": "m1-rationalist",
    "Empiricist":  "m1-empiricist",
    "Coherentist": "m1-coherentist",
    "Pragmatist":  "m1-pragmatist",
    "Standpoint":  "m1-standpoint",
}
ORCHESTRATOR_MODEL = "m1-council-orchestrator"

INPUT_CSV  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mmlu_hard_subset.csv")
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mmlu_hard_subset_results_council.csv")
PHASE_LOG_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mmlu_hard_subset_council_phaselog.csv")

# ─── Output CSV columns ───────────────────────────────────────────────────────
PHASE_LABELS = ["P1", "P2", "P3"]  # 3 debate phases (Phase 4 = orchestrator)
BASE_INPUT_COLS = ["Row_Index", "Question", "A", "B", "C", "D", "Answer", "Subject"]

PER_MODEL_COLS = []
for phase in PHASE_LABELS:
    for agent in AGENTS:
        PER_MODEL_COLS.append(f"{phase}_{agent}_Answer")
        PER_MODEL_COLS.append(f"{phase}_{agent}_Confidence")

OUTPUT_FIELDS = (
    BASE_INPUT_COLS
    + PER_MODEL_COLS
    + ["LLM_Answer", "LLM_Confidence", "Consensus_Method",
       "Agreement_Ratio", "LLM_Raw_Response", "Council_Debate_Log"]
)

# Phase log: one row per (question, phase, agent) — written immediately
PHASE_LOG_FIELDS = [
    "Row_Index", "Subject", "Correct_Answer",
    "Phase", "Agent", "Answer", "Confidence", "Raw_Response",
]


# ─── API Helpers ──────────────────────────────────────────────────────────────

def call_model(model_name: str, content: str) -> str:
    """
    Call a local model via the Anthropic Messages API format.
    Sends only a user-role message — no system prompt (baked into model).
    Does NOT send max_tokens (configured on the server side).
    """
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": content}],
    }
    headers = {"Content-Type": "application/json"}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(API_URL, json=payload, headers=headers, timeout=300)
            resp.raise_for_status()
            data = resp.json()

            # Handle both Anthropic-style (content list) and OpenAI-style (choices) responses
            content_blocks = data.get("content", [])
            if isinstance(content_blocks, list) and content_blocks:
                parts = []
                for block in content_blocks:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block["text"])
                    elif isinstance(block, str):
                        parts.append(block)
                return "".join(parts)

            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")

            return f"ERROR: Unrecognised response format: {data}"

        except Exception as e:
            print(f"    ⚠ [{model_name}] Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
            else:
                if "500" in str(e):
                    print(f"\n\n🛑 FATAL: 500 Server Error from local proxy for {model_name}.\n    Halting evaluation as requested.", flush=True)
                    import os
                    os._exit(1)
                return f"ERROR: {e}"


def call_models_sequential(
    model_contents: Dict[str, str],
    phase_label: str = "",
    row_index: int = -1,
    subject: str = "",
    correct_answer: str = "",
    phase_log_writer=None,
    phase_log_file=None,
) -> Dict[str, str]:
    """
    Call multiple models one at a time (sequential).
    Writes each model's response to the phase log immediately after receipt.
    """
    results = {}
    for agent, content in model_contents.items():
        response = call_model(AGENT_MODELS[agent], content)
        results[agent] = response

        # ── Flush to phase log immediately ────────────────────────────────────
        if phase_log_writer is not None:
            ans, conf = parse_answer_confidence(response)
            phase_log_writer.writerow({
                "Row_Index":     row_index,
                "Subject":       subject,
                "Correct_Answer": correct_answer,
                "Phase":         phase_label,
                "Agent":         agent,
                "Answer":        ans,
                "Confidence":    conf,
                "Raw_Response":  response,
            })
            if phase_log_file:
                phase_log_file.flush()

        time.sleep(INTER_MODEL_DELAY)  # brief pause between models
    return results

def call_models_parallel(
    model_contents: Dict[str, str],
    phase_label: str = "",
    row_index: int = -1,
    subject: str = "",
    correct_answer: str = "",
    phase_log_writer=None,
    phase_log_file=None,
) -> Dict[str, str]:
    """
    Call multiple models in parallel using a thread pool.
    Writes each model's response to the phase log immediately after receipt.
    """
    results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_agent = {

            executor.submit(call_model, AGENT_MODELS[agent], content): agent
            for agent, content in model_contents.items()
        }
        for future in as_completed(future_to_agent):
            agent = future_to_agent[future]
            try:
                response = future.result(timeout=310)
            except Exception as e:
                response = f"ERROR: {e}"
            results[agent] = response

            # ── Flush to phase log immediately ────────────────────────────────────
            if phase_log_writer is not None:
                ans, conf = parse_answer_confidence(response)
                phase_log_writer.writerow({
                    "Row_Index":     row_index,
                    "Subject":       subject,
                    "Correct_Answer": correct_answer,
                    "Phase":         phase_label,
                    "Agent":         agent,
                    "Answer":        ans,
                    "Confidence":    conf,
                    "Raw_Response":  response,
                })
                if phase_log_file:
                    phase_log_file.flush()
    return results


# ─── Parsing ──────────────────────────────────────────────────────────────────

def parse_answer_confidence(text: str) -> Tuple[str, str]:
    """
    Extract Answer letter and Confidence % from the END of a response string.
    Searching from the end avoids matching quoted answers from other models.
    """
    # Find all occurrences and take the LAST one
    answer = ""
    confidence = ""

    answer_matches = list(re.finditer(r"Answer\s*:\s*([A-Da-d])", text))
    if answer_matches:
        answer = answer_matches[-1].group(1).upper()

    confidence_matches = list(re.finditer(r"Confidence\s*:\s*(\d+)\s*%?", text))
    if confidence_matches:
        confidence = confidence_matches[-1].group(1)

    return answer, confidence


def build_transcript(phase_label: str, responses: Dict[str, str]) -> str:
    """Format a phase's responses into a readable transcript block."""
    lines = [f"=== {phase_label} ==="]
    for agent in AGENTS:
        lines.append(f"\n[{agent}]:\n{responses.get(agent, 'No response.')}")
    return "\n".join(lines)


# ─── Prompt Builders ──────────────────────────────────────────────────────────

def build_phase1_prompt(question: str, a: str, b: str, c: str, d: str) -> str:
    return (
        f"Question: {question}\n"
        f"A) {a}\n"
        f"B) {b}\n"
        f"C) {c}\n"
        f"D) {d}\n\n"
        f"Reason through this question using your epistemological framework. "
        f"At the very end of your response, on a new line, provide your verdict exactly as:\n"
        f"Answer: [A/B/C/D] Confidence: [0-100]%"
    )


def build_phase2_prompt(p1_transcript: str) -> str:
    return (
        f"Here are the opening statements from the other council members:\n\n"
        f"{p1_transcript}\n\n"
        f"Critique the logic, evidence, and reasoning of the other members. "
        f"Identify any flaws or contradictions and defend your own epistemological position. "
        f"At the very end of your response, on a new line, provide your revised verdict exactly as:\n"
        f"Answer: [A/B/C/D] Confidence: [0-100]%"
    )


def build_phase3_prompt(p1_transcript: str, p2_transcript: str) -> str:
    return (
        f"You have seen the opening statements and the first round of critiques:\n\n"
        f"{p1_transcript}\n\n"
        f"{p2_transcript}\n\n"
        f"Having considered all arguments and counterarguments, provide your FINAL position. "
        f"At the very end of your response, on a new line, provide your final verdict exactly as:\n"
        f"Answer: [A/B/C/D] Confidence: [0-100]%"
    )


def build_orchestrator_prompt_majority(
    full_debate: str, majority_answer: str, vote_count: int
) -> str:
    return (
        f"The council has debated the following question:\n\n"
        f"{full_debate}\n\n"
        f"After three rounds of debate, {vote_count} out of 5 council members "
        f"reached a majority verdict of Answer: {majority_answer}.\n"
        f"Review the debate and calibrate the final confidence score for this consensus answer.\n"
        f"Output exactly:\nAnswer: {majority_answer} Confidence: [0-100]%"
    )


def build_orchestrator_prompt_tiebreak(full_debate: str) -> str:
    return (
        f"The council has debated the following question:\n\n"
        f"{full_debate}\n\n"
        f"The council is SPLIT — no majority was reached after three rounds of debate. "
        f"As orchestrator, review all arguments and determine which answer has the strongest "
        f"epistemological support across all traditions. "
        f"Act as a true mediator: weigh logical validity, empirical grounding, "
        f"systemic coherence, practical utility, and situated context.\n"
        f"At the very end of your response, output exactly:\n"
        f"Answer: [A/B/C/D] Confidence: [0-100]%"
    )


# ─── Per-question Council Run ─────────────────────────────────────────────────

def run_council_for_question(
    row_index: int,
    question: str, a: str, b: str, c: str, d: str,
    correct_answer: str, subject: str,
    phase_log_writer=None,
    phase_log_file=None,
) -> dict:
    """
    Run the full 4-phase council debate for a single question.
    Returns a dict of all output fields for writing to CSV.
    phase_log_writer: csv.DictWriter for the live phase log (optional)
    """
    print(f"\n[{row_index}] Subject: {subject} | Correct: {correct_answer}")
    out = {}

    # common kwargs forwarded to call_models_sequential
    log_kwargs = dict(
        row_index=row_index,
        subject=subject,
        correct_answer=correct_answer,
        phase_log_writer=phase_log_writer,
        phase_log_file=phase_log_file,
    )

    # ── Phase 1: Independent Opening (parallel) ─────────────────────────────
    print("  ▶ Phase 1: Independent opening statements...")
    p1_prompt = build_phase1_prompt(question, a, b, c, d)
    p1_responses = call_models_parallel(
        {agent: p1_prompt for agent in AGENTS},
        phase_label="P1", **log_kwargs
    )
    p1_transcript = build_transcript("Phase 1 — Opening Statements", p1_responses)

    for agent in AGENTS:
        ans, conf = parse_answer_confidence(p1_responses.get(agent, ""))
        out[f"P1_{agent}_Answer"]     = ans
        out[f"P1_{agent}_Confidence"] = conf

    # ── Phase 2: Critique Round 1 (parallel) ───────────────────────────────
    print("  ▶ Phase 2: Critique round 1...")
    p2_prompt = build_phase2_prompt(p1_transcript)
    p2_responses = call_models_parallel(
        {agent: p2_prompt for agent in AGENTS},
        phase_label="P2", **log_kwargs
    )
    p2_transcript = build_transcript("Phase 2 — Critique Round 1", p2_responses)

    for agent in AGENTS:
        ans, conf = parse_answer_confidence(p2_responses.get(agent, ""))
        out[f"P2_{agent}_Answer"]     = ans
        out[f"P2_{agent}_Confidence"] = conf

    # ── Phase 3: Critique Round 2 (parallel) ───────────────────────────────
    print("  ▶ Phase 3: Critique round 2 (final positions)...")
    p3_prompt = build_phase3_prompt(p1_transcript, p2_transcript)
    p3_responses = call_models_parallel(
        {agent: p3_prompt for agent in AGENTS},
        phase_label="P3", **log_kwargs
    )
    p3_transcript = build_transcript("Phase 3 — Critique Round 2 / Final Positions", p3_responses)

    for agent in AGENTS:
        ans, conf = parse_answer_confidence(p3_responses.get(agent, ""))
        out[f"P3_{agent}_Answer"]     = ans
        out[f"P3_{agent}_Confidence"] = conf

    # ── Phase 4: Consensus Resolution ─────────────────────────────────────────
    print("  ▶ Phase 4: Consensus resolution...")
    full_debate = f"{p1_transcript}\n\n{p2_transcript}\n\n{p3_transcript}"

    # Count Phase 3 final answers
    p3_answers = [out[f"P3_{agent}_Answer"] for agent in AGENTS if out[f"P3_{agent}_Answer"]]
    vote_tally = Counter(p3_answers)
    top_answer, top_count = vote_tally.most_common(1)[0] if vote_tally else ("", 0)

    if top_count >= 3:
        # Majority achieved — orchestrator confirms and calibrates confidence
        consensus_method = "majority"
        agreement_ratio  = f"{top_count}/5"
        print(f"     Majority: {top_answer} ({top_count}/5 votes) → orchestrator calibrating confidence...")
        orch_prompt  = build_orchestrator_prompt_majority(full_debate, top_answer, top_count)
        orch_response = call_model(ORCHESTRATOR_MODEL, orch_prompt)
        final_answer, final_conf = parse_answer_confidence(orch_response)
        # Trust the majority answer even if orchestrator's parse fails
        if not final_answer:
            final_answer = top_answer
    else:
        # No majority — orchestrator tiebreaks
        consensus_method = "orchestrator_tiebreak"
        agreement_ratio  = f"{top_count}/5"
        print(f"     No majority (split: {dict(vote_tally)}) → orchestrator tiebreaking...")
        orch_prompt   = build_orchestrator_prompt_tiebreak(full_debate)
        orch_response = call_model(ORCHESTRATOR_MODEL, orch_prompt)
        final_answer, final_conf = parse_answer_confidence(orch_response)

    match = "✅" if final_answer == correct_answer else "❌"
    print(f"     Consensus: {final_answer} | Confidence: {final_conf}% | {match} | Method: {consensus_method}")

    # ── Phase 4 also logged ───────────────────────────────────────────────────
    if phase_log_writer is not None:
        orch_ans, orch_conf = parse_answer_confidence(orch_response)
        phase_log_writer.writerow({
            "Row_Index":      row_index,
            "Subject":        subject,
            "Correct_Answer": correct_answer,
            "Phase":          "P4_Orchestrator",
            "Agent":          "Orchestrator",
            "Answer":         orch_ans,
            "Confidence":     orch_conf,
            "Raw_Response":   orch_response,
        })
        if phase_log_file:
            phase_log_file.flush()

    out["LLM_Answer"]        = final_answer
    out["LLM_Confidence"]    = final_conf
    out["Consensus_Method"]  = consensus_method
    out["Agreement_Ratio"]   = agreement_ratio
    out["LLM_Raw_Response"]  = orch_response
    out["Council_Debate_Log"] = full_debate

    return out


# ─── Resume Support ───────────────────────────────────────────────────────────

def load_completed_indices(output_path: str) -> set:
    completed = set()
    if not os.path.exists(output_path):
        return completed
    try:
        with open(output_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                idx = row.get("Row_Index")
                if idx is not None:
                    completed.add(int(idx))
    except Exception:
        pass
    return completed


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Epistemic Council MMLU Evaluation")
    parser.add_argument("--limit",  type=int, default=None, help="Only evaluate first N questions")
    parser.add_argument("--resume", action="store_true",    help="Resume from a previous partial run")
    args = parser.parse_args()

    # Read input CSV
    rows = []
    with open(INPUT_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    total = len(rows)
    limit = min(args.limit, total) if args.limit else total
    print(f"📋 Loaded {total} questions from {INPUT_CSV}")
    print(f"🎯 Will evaluate {limit} question(s) through the Epistemic Council\n")

    # Resume support
    completed = set()
    if args.resume:
        completed = load_completed_indices(OUTPUT_CSV)
        if completed:
            print(f"♻️  Resume mode: {len(completed)} questions already done, skipping.\n")

    # Prepare output CSVs
    write_header = not (args.resume and os.path.exists(OUTPUT_CSV) and len(completed) > 0)
    mode = "w" if write_header else "a"
    outfile = open(OUTPUT_CSV, mode, newline="", encoding="utf-8")
    writer  = csv.DictWriter(outfile, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
    if write_header:
        writer.writeheader()

    # Phase log — always append so partial runs accumulate
    phase_log_exists = os.path.exists(PHASE_LOG_CSV) and args.resume
    phase_log_file = open(PHASE_LOG_CSV, "a" if phase_log_exists else "w", newline="", encoding="utf-8")
    phase_log_writer = csv.DictWriter(phase_log_file, fieldnames=PHASE_LOG_FIELDS, extrasaction="ignore")
    if not phase_log_exists:
        phase_log_writer.writeheader()
    print(f"📝 Phase log:    {PHASE_LOG_CSV}")

    success_count  = 0
    error_count    = 0
    majority_count = 0
    tiebreak_count = 0

    try:
        for i, row in enumerate(rows[:limit]):
            if i in completed:
                continue

            question = row.get("Question", "").strip()
            a        = row.get("A", "").strip()
            b        = row.get("B", "").strip()
            c        = row.get("C", "").strip()
            d        = row.get("D", "").strip()
            correct  = row.get("Answer", "").strip()
            subject  = row.get("Subject", "").strip()

            result = run_council_for_question(
                i, question, a, b, c, d, correct, subject,
                phase_log_writer=phase_log_writer,
                phase_log_file=phase_log_file,
            )

            # Track stats
            if result.get("LLM_Answer", "").startswith("ERROR"):
                error_count += 1
            else:
                success_count += 1
            if result.get("Consensus_Method") == "majority":
                majority_count += 1
            else:
                tiebreak_count += 1

            # Write row
            out_row = {"Row_Index": i}
            out_row.update({k: row.get(k, "") for k in ["Question", "A", "B", "C", "D", "Answer", "Subject"]})
            out_row.update(result)
            writer.writerow(out_row)
            outfile.flush()

            # Small pause between questions to be gentle on the server
            if i < limit - 1:
                time.sleep(2)

    except KeyboardInterrupt:
        print(f"\n\n⚠️  Interrupted! {success_count} questions completed so far.")
        print("    Run with --resume to continue.")
    finally:
        outfile.close()
        phase_log_file.close()

    # Summary
    print(f"\n{'='*65}")
    print(f"📊 Council Evaluation Complete!")
    print(f"   ✅ Successful:      {success_count}")
    print(f"   ❌ Errors:          {error_count}")
    print(f"   🗳️  Majority votes: {majority_count}")
    print(f"   ⚖️  Tiebreaks:      {tiebreak_count}")
    print(f"   📁 Results saved:  {OUTPUT_CSV}")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()
