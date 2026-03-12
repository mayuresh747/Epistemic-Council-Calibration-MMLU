#!/usr/bin/env python3
import requests
import json
import time
import os
import re
from typing import List, Dict

# --- Configuration ---
API_URL = "http://localhost:8001/v1/messages"
MODEL = "gpt-4o" # Or your local model name
MAX_TOKENS = 1024

# --- Epistemological System Prompts ---

SYSTEM_PROMPTS = {
    "Rationalist": (
        "You are the Rationalist Agent. Your world is governed by the Principle of Sufficient Reason. "
        "You hold that sensory data is deceptive and that truth is found only through deduction from 'First Principles'. "
        "If a claim is logically inconsistent, it is impossible. "
        "Thought Requirement: In your <thought> block, you must construct a formal SYLLOGISM (Major Premise, Minor Premise, Conclusion) "
        "that necessitates your answer. Focus on WHY it MUST be so."
    ),
    "Empiricist": (
        "You are the Empiricist Agent. You believe that 'logical necessity' is often just a hallucination of the mind. "
        "Knowledge is built strictly through measurement, observation, and induction. "
        "Thought Requirement: In your <thought> block, you must perform a FALSIFIABILITY CHECK: what specific observation "
        "would prove this idea wrong? Demand error bars and brute evidence. If it hasn't been measured, it isn't real."
    ),
    "Coherentist": (
        "You are the Coherentist Agent. You believe truth is a property of the 'Web of Belief'. "
        "A fact is only true if it fits into the broader structure of human knowledge without contradiction. "
        "Thought Requirement: In your <thought> block, you must map the SYSTEMIC DEPENDENCIES: if we accept this claim, "
        "what else must we change in our worldview to keep it consistent? Focus on holistic fit."
    ),
    "Pragmatist": (
        "You are the Pragmatist Agent. Truth is a tool measured by its 'cash value' in action. "
        "If a belief leads to successful predictions and engineering triumphs, it is functionally true. "
        "Thought Requirement: In your <thought> block, you must calculate the UTILITY DELTA: describe the specific "
        "human actions or technological outcomes enabled by this belief. Focus on WHAT WORKS."
    ),
    "Standpoint": (
        "You are the Standpoint Epistemologist. You believe knowledge is situated and scientific authority "
        "reflects historical power dynamics. There is no 'View from Nowhere'. "
        "Thought Requirement: In your <thought> block, perform an EPISTEMIC GENEALOGY: trace the history of this idea "
        "and identify the social/power structures that allowed it to become 'common sense'. Challenge 'universal' claims."
    ),
    "Orchestrator": (
        "You are the Council Orchestrator. Your job is to synthesize the intense debate between "
        "the Rationalist, Empiricist, Coherentist, Pragmatist, and Standpoint agents. "
        "Acknowledge the epistemological tensions and provide a final, collective answer that honors "
        "the most robust arguments from each philosophical tradition."
    )
}

# --- Model Mapping ---
AGENT_MODELS = {
    "Rationalist": "M1-Rationalist",
    "Empiricist": "M1-Empiricist",
    "Coherentist": "M1-Coherentist",
    "Pragmatist": "M1-Pragmatist",
    "Standpoint": "M1-Standpoint",
    "Orchestrator": "M1-Council-Orchestrator"
}

def call_nebula(model_name: str, messages: List[Dict]) -> str:
    """Standardized call to your local Nebula server."""
    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "temperature": 0.7
    }
    try:
        resp = requests.post(API_URL, json=payload, timeout=300) # Increased to 5 mins
        resp.raise_for_status()
        data = resp.json()
        
        # Adjusting to handle both Anthropic and OpenAI-like response formats
        content = data.get("content", [])
        if isinstance(content, list) and len(content) > 0:
            text = content[0].get("text", "")
        else:
            choices = data.get("choices", [])
            text = choices[0].get("message", {}).get("content", "") if choices else "No response."
            
        print(f"\n--- {model_name} Response ---\n{text}\n")
        return text
    except Exception as e:
        error_msg = f"Error calling {model_name}: {e}"
        print(f"\n!!! {error_msg} !!!\n")
        return error_msg

def run_council(question: str):
    print(f"\n[ORCHESTRATOR] Starting Council for: {question}")
    
    # Phase 1: Sequential Opening Statements
    # Each agent hears the ones before it to build the initial context
    transcript_p1 = []
    agent_responses_p1 = {}

    for name in ["Rationalist", "Empiricist", "Coherentist", "Pragmatist", "Standpoint"]:
        print(f"  > {name} is taking the floor...")
        
        # Build the 'Council Minutes' so far
        context = [{"role": "user", "content": question}]
        if transcript_p1:
            context.append({"role": "assistant", "content": "\n".join(transcript_p1)})
            context.append({"role": "user", "content": f"You have heard the previous members. Now, {name}, provide your perspective."})
        
        response = call_nebula(AGENT_MODELS[name], context)
        agent_responses_p1[name] = response
        transcript_p1.append(f"[{name}]: {response}")

    # Phase 2: Cross-Examination
    # Now every agent sees the FULL transcript and critiques everyone else
    print(f"\n[ORCHESTRATOR] Phase 2: Cross-Examination & Critique")
    full_transcript_text = "\n\n".join(transcript_p1)
    transcript_p2 = []

    for name in ["Rationalist", "Empiricist", "Coherentist", "Pragmatist", "Standpoint"]:
        print(f"  > {name} is reviewing the council's logic...")
        
        critique_prompt = (
            f"Here is the full transcript of the Council's initial perspectives:\n\n"
            f"{full_transcript_text}\n\n"
            f"As the {name}, you must now question the logic, evidence, or utility of the other members. "
            f"Identify contradictions and defend your epistemology against their claims. "
            f"Take your time to reason through the flaws in their arguments."
        )
        
        response = call_nebula(AGENT_MODELS[name], [{"role": "user", "content": critique_prompt}])
        transcript_p2.append(f"[{name}'s Critique]: {response}")

    # Phase 3: Final Synthesis
    print(f"\n[ORCHESTRATOR] Phase 3: Final Synthesis")
    final_debate = "\n\n".join(transcript_p2)
    
    synthesis_prompt = (
        f"The Council has completed its debate on: '{question}'\n\n"
        f"Initial Statements:\n{full_transcript_text}\n\n"
        f"Cross-Examination & Critiques:\n{final_debate}\n\n"
        f"Synthesize this intense epistemological conflict and provide the user with a "
        f"collective final recommendation that honors the best arguments from all sides."
    )
    
    final_answer = call_nebula(AGENT_MODELS["Orchestrator"], [{"role": "user", "content": synthesis_prompt}])
    
    print(f"\n--- FINAL COLLECTIVE ANSWER ---\n")
    print(final_answer)

if __name__ == "__main__":
    import sys
    user_q = "Why does gravity exist and how do we know it is true?"
    if len(sys.argv) > 1:
        user_q = " ".join(sys.argv[1:])
    run_council(user_q)
