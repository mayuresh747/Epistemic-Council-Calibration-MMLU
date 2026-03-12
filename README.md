# Epistemic Council MMLU Evaluation

This repository contains the scripts, logs, and evaluation results for comparing a standard single-agent language model (baseline) against a multi-agent "Epistemic Council" architecture on the Massive Multitask Language Understanding (MMLU) hard subset.

## Experiment Setup

The Epistemic Council architecture utilizes five distinct agents, each explicitly prompted to operate under a specific philosophical framework, alongside an Orchestrator agent to synthesize debate and calibrate final confidence.

*   **Rationalist:** Focuses on logical necessity, formal syllogisms, and deduction. 
*   **Empiricist:** Builds knowledge strictly through measurement, observation, and falsifiability checks.
*   **Coherentist:** Evaluates truth based on systemic dependencies and holistic fit within a "Web of Belief."
*   **Pragmatist:** Measures truth by practical outcomes, utility delta, and "what works."
*   **Standpoint:** Challenges universal claims by tracing epistemic genealogy and analyzing power dynamics.

### The 4-Phase Debate Process

1.  **Independent Opening (Phase 1):** All 5 agents evaluate the question and provide an initial answer in parallel, with no cross-talk.
2.  **Critique Round 1 (Phase 2):** Agents review the Phase 1 transcript, actively critiquing the logic and evidence of their peers while defending their own epistemic position.
3.  **Critique Round 2 (Phase 3):** Agents review the accumulated debate transcript and submit their final, revised verdict and confidence score.
4.  **Consensus Resolution (Phase 4):** A majority vote is taken based on Phase 3 answers. If the council is split without a majority, the Orchestrator steps in to mediate and break the tie based on the strength of the preceding arguments.

---

## Key Findings

The Epistemic Council architecture demonstrated a significant improvement over the baseline model on the exact same 100 difficult MMLU questions.

*   **Baseline Accuracy:** 70%
*   **Council Accuracy:** 86%
*   **Net Improvement:** +16%

### Outcome Breakdown

The council actively improved upon the baseline by getting 21 questions correct that the baseline failed on, while only regressing on 5 questions.

*   **Both Correct:** 65 questions
*   **Council Improved:** 21 questions 
*   **Council Regressed:** 5 questions
*   **Both Incorrect:** 9 questions

![Accuracy Comparison](accuracy_bar_chart.png)
![Outcome Distribution](outcomes_pie_chart.png)

---

## Phase-wise Analysis: Debate Evolution

Tracking how the agents changed their minds and converged on a solution shows the power of structured peer critique.

**Answer Changes:**
*   From Phase 1 to Phase 2: 50 individual agent answers changed (out of ~500).
*   From Phase 2 to Phase 3: Only 22 answers changed as positions solidified.

**Growth of Consensus:**
The council naturally converged toward unanimity without needing the Orchestrator to break ties.
*   **Phase 1:** 75 Unanimous, 20 Majority, 3 Split
*   **Phase 2:** 86 Unanimous, 13 Majority, 1 Split
*   **Phase 3:** 93 Unanimous, 7 Majority, **0 Split**

**Deep Dive on "Council Improved" Cases (n=21)**
On the 21 questions where the baseline model failed, the council showed early strength. Even in Phase 1 (independent reasoning), the majority vote accuracy was already 81%. By Phase 3, unanimous agreement on these difficult questions grew from 11 to 19. Forcing diverse epistemic constraints prevented the single-path "echo chamber" failure mode of the baseline model.

---

## Model Calibration & Reliability

The Orchestrator explicitly calibrates confidence scores based on the council consensus and debate margins. The reliability diagrams below map the mean accuracy of the models against their mean reported confidence, showing how the Council aligns its certainty with its actual performance better than the baseline.

### Baseline Agent Calibration
![Baseline Calibration Plot](mmlu_hard_subset_results_nebula_gpt5.1_calibration_plot.png)

### Epistemic Council Calibration
![Council Calibration Plot](mmlu_hard_subset_results_council_calibration_plot.png)

---

## Repository Contents

*   `run_mmlu_eval.py`: Standard baseline evaluation script.
*   `run_mmlu_eval_council.py`: Orchestrates the 4-phase debate process.
*   `council_orchestrator.py`: Definitions of the system prompts and orchestration logic.
*   `analyze_calibration.py` / `analyze_phases.py`: Scripts used to generate the charts and parse the phase logs.
*   `mmlu_hard_subset.csv`: The input questions.
*   `mmlu_hard_subset_results_nebula_gpt5.1.csv`: The baseline outputs.
*   `mmlu_hard_subset_results_council.csv`: The final council outputs.
*   `mmlu_hard_subset_council_phaselog.csv`: The raw transcript of all agent votes and text across all phases.
*   `mmlu_comparison_baseline_vs_council.csv`: Side-by-side comparison categorizing the outcomes.
