#!/usr/bin/env python3
"""
MMLU Hard Subset Evaluation Script

Sends each question from mmlu_hard_subset.csv to the nebula server (model: gpt51-normal)
via the Anthropic Messages API, parses the LLM's answer and confidence, and saves results
to mmlu_hard_subset_results.csv.

Usage:
    python3 run_mmlu_eval.py                 # Run all 100 questions
    python3 run_mmlu_eval.py --limit 5       # Run only the first 5 questions
    python3 run_mmlu_eval.py --resume        # Resume from where a previous run left off
"""

import csv
import json
import re
import time
import argparse
import os
import requests
from typing import Optional, Tuple

# ─── Configuration ───────────────────────────────────────────────────────────
API_URL = "http://localhost:8001/v1/messages"
MODEL = "gpt51-empiricist"
MAX_TOKENS = 256
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

INPUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mmlu_hard_subset.csv")
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mmlu_hard_subset_results.csv")


def build_prompt(question: str, opt_a: str, opt_b: str, opt_c: str, opt_d: str) -> str:
    """Build the prompt to send to the model. Does NOT include the correct answer."""
    return (
        f"Question: {question} "
        f"A) {opt_a} "
        f"B) {opt_b} "
        f"C) {opt_c} "
        f"D) {opt_d}\n\n"
        f"Answer the question and provide your confidence level. "
        f"Format your response exactly as follows: Answer: [Letter] Confidence: [0-100]%"
    )


def call_llm(prompt: str) -> str:
    """Send a single prompt to the nebula server and return the text response."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": MAX_TOKENS,
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(API_URL, json=payload, headers=headers, timeout=120)
            resp.raise_for_status()
            data = resp.json()

            # Anthropic Messages API returns content as a list of blocks
            content_blocks = data.get("content", [])
            text_parts = []
            for block in content_blocks:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block["text"])
                elif isinstance(block, str):
                    text_parts.append(block)
            return "".join(text_parts) if text_parts else str(data)

        except Exception as e:
            print(f"    ⚠ Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
            else:
                return f"ERROR: {e}"


def parse_response(raw: str) -> Tuple[str, str]:
    """
    Extract the answer letter and confidence from the LLM response.
    Returns (answer_letter, confidence_pct).
    """
    answer = ""
    confidence = ""

    # Try to find "Answer: X"
    m = re.search(r"Answer\s*:\s*([A-Da-d])", raw)
    if m:
        answer = m.group(1).upper()

    # Try to find "Confidence: XX%"
    m = re.search(r"Confidence\s*:\s*(\d+)\s*%", raw)
    if m:
        confidence = m.group(1)

    return answer, confidence


def load_completed_indices(output_path: str) -> set:
    """If the output CSV already exists, return the set of already-completed row indices."""
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


def main():
    parser = argparse.ArgumentParser(description="Run MMLU Hard Subset evaluation")
    parser.add_argument("--limit", type=int, default=None, help="Only evaluate the first N questions")
    parser.add_argument("--resume", action="store_true", help="Resume from a previous partial run")
    args = parser.parse_args()

    # ─── Read input CSV ──────────────────────────────────────────────────
    rows = []
    with open(INPUT_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    total = len(rows)
    limit = min(args.limit, total) if args.limit else total
    print(f"📋 Loaded {total} questions from {INPUT_CSV}")
    print(f"🎯 Will evaluate {limit} question(s) using model '{MODEL}' on {API_URL}\n")

    # ─── Resume support ──────────────────────────────────────────────────
    completed = set()
    if args.resume:
        completed = load_completed_indices(OUTPUT_CSV)
        if completed:
            print(f"♻️  Resume mode: {len(completed)} questions already completed, skipping them.\n")

    # ─── Prepare output CSV ──────────────────────────────────────────────
    output_fields = ["Row_Index"] + list(rows[0].keys()) + ["LLM_Answer", "LLM_Confidence", "LLM_Raw_Response"]

    # Open in append mode if resuming, write mode otherwise
    write_header = not (args.resume and os.path.exists(OUTPUT_CSV) and len(completed) > 0)
    mode = "w" if write_header else "a"

    outfile = open(OUTPUT_CSV, mode, newline="", encoding="utf-8")
    writer = csv.DictWriter(outfile, fieldnames=output_fields, extrasaction="ignore")
    if write_header:
        writer.writeheader()

    # ─── Evaluate each question ──────────────────────────────────────────
    success_count = 0
    error_count = 0

    try:
        for i, row in enumerate(rows[:limit]):
            if i in completed:
                continue

            question = row.get("Question", "").strip()
            opt_a = row.get("A", "").strip()
            opt_b = row.get("B", "").strip()
            opt_c = row.get("C", "").strip()
            opt_d = row.get("D", "").strip()
            correct_answer = row.get("Answer", "").strip()
            subject = row.get("Subject", "").strip()

            print(f"[{i+1}/{limit}] Subject: {subject} | Correct: {correct_answer}")

            # Build prompt (NO correct answer sent to model)
            prompt = build_prompt(question, opt_a, opt_b, opt_c, opt_d)

            # Call the LLM
            raw_response = call_llm(prompt)
            llm_answer, llm_confidence = parse_response(raw_response)

            match = "✅" if llm_answer == correct_answer else "❌"
            print(f"         LLM Answer: {llm_answer} | Confidence: {llm_confidence}% | {match}")

            if raw_response.startswith("ERROR:"):
                error_count += 1
            else:
                success_count += 1

            # Write result row
            out_row = {"Row_Index": i}
            out_row.update(row)
            out_row["LLM_Answer"] = llm_answer
            out_row["LLM_Confidence"] = llm_confidence
            out_row["LLM_Raw_Response"] = raw_response
            writer.writerow(out_row)
            outfile.flush()  # Flush after each row so partial results are saved

            # Small delay between requests to be gentle on the server
            if i < limit - 1:
                time.sleep(1)

    except KeyboardInterrupt:
        print(f"\n\n⚠️  Interrupted! {success_count} questions completed so far.")
        print(f"    Run with --resume to continue from where you left off.")
    finally:
        outfile.close()

    # ─── Summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"📊 Evaluation Complete!")
    print(f"   ✅ Successful: {success_count}")
    print(f"   ❌ Errors:     {error_count}")
    print(f"   📁 Results saved to: {OUTPUT_CSV}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
