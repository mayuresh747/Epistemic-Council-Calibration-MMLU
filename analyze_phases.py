import pandas as pd
import numpy as np

# Load data
df_log = pd.read_csv('/Users/mayuri/Projects/Eval/mmlu_hard_subset_council_phaselog.csv')
df_baseline = pd.read_csv('/Users/mayuri/Projects/Eval/mmlu_comparison_baseline_vs_council.csv')

# Merge to get Outcome in the log
df_log = df_log.merge(df_baseline[['Row_Index', 'Outcome']], on='Row_Index', how='left')

agents = ['Rationalist', 'Empiricist', 'Coherentist', 'Pragmatist', 'Standpoint']

# Pivot log to see answers per phase per agent
# P1
df_p1 = df_log[df_log['Phase'] == 'P1']
# P2
df_p2 = df_log[df_log['Phase'] == 'P2']
# P3
df_p3 = df_log[df_log['Phase'] == 'P3']

print("=== Phase Analysis ===")

# Agent Answer Changes
def get_changes(df_early, df_late):
    merged = df_early.merge(df_late, on=['Row_Index', 'Agent'], suffixes=('_early', '_late'))
    changed = merged[merged['Answer_early'] != merged['Answer_late']]
    return len(changed), len(merged)

p1_p2_changes, p1_p2_total = get_changes(df_p1, df_p2)
p2_p3_changes, p2_p3_total = get_changes(df_p2, df_p3)
print(f"Answer changes P1 -> P2: {p1_p2_changes} out of {p1_p2_total} agent-questions")
print(f"Answer changes P2 -> P3: {p2_p3_changes} out of {p2_p3_total} agent-questions")

# Agreement (Consensus)
def get_agreement(df_phase):
    # For each question, count the max votes for any single answer
    votes = df_phase.groupby(['Row_Index', 'Answer']).size().reset_index(name='count')
    max_votes = votes.groupby('Row_Index')['count'].max()
    unanimous = (max_votes == 5).sum()
    majority = ((max_votes >= 3) & (max_votes < 5)).sum()
    split = (max_votes < 3).sum()
    return unanimous, majority, split

u1, m1, s1 = get_agreement(df_p1)
u2, m2, s2 = get_agreement(df_p2)
u3, m3, s3 = get_agreement(df_p3)

print(f"P1 Agreement: {u1} Unanimous, {m1} Majority, {s1} Split")
print(f"P2 Agreement: {u2} Unanimous, {m2} Majority, {s2} Split")
print(f"P3 Agreement: {u3} Unanimous, {m3} Majority, {s3} Split")

# Phase Accuracy
def get_accuracy(df_phase):
    # Majority vote accuracy
    def get_maj_ans(group):
        modes = group['Answer'].dropna().mode()
        if len(modes) == 0: return None
        return modes.iloc[0]
    
    maj_ans = df_phase.groupby('Row_Index').apply(get_maj_ans).reset_index(name='Maj_Answer')
    correct = df_phase[['Row_Index', 'Correct_Answer']].drop_duplicates()
    merged = maj_ans.merge(correct, on='Row_Index')
    acc = (merged['Maj_Answer'] == merged['Correct_Answer']).mean()
    return acc

acc_p1 = get_accuracy(df_p1)
acc_p2 = get_accuracy(df_p2)
acc_p3 = get_accuracy(df_p3)
print(f"Majority Vote Accuracy P1: {acc_p1:.1%}")
print(f"Majority Vote Accuracy P2: {acc_p2:.1%}")
print(f"Majority Vote Accuracy P3: {acc_p3:.1%}")

# Confidence Evolution
conf_p1 = df_p1['Confidence'].mean()
conf_p2 = df_p2['Confidence'].mean()
conf_p3 = df_p3['Confidence'].mean()
print(f"Average Confidence P1: {conf_p1:.1f}%")
print(f"Average Confidence P2: {conf_p2:.1f}%")
print(f"Average Confidence P3: {conf_p3:.1f}%")

# Orchestrator Phase (P4)
df_p4 = df_log[df_log['Phase'] == 'P4_Orchestrator']
acc_p4 = (df_p4['Answer'] == df_p4['Correct_Answer']).mean()
print(f"Orchestrator Accuracy: {acc_p4:.1%}")

# Focus on "Council Improved" (21 questions)
print("\n=== For the 21 'Council Improved' questions ===")
df_improved = df_log[df_log['Outcome'] == 'Council Improved']
df_imp_p1 = df_improved[df_improved['Phase'] == 'P1']
df_imp_p3 = df_improved[df_improved['Phase'] == 'P3']

u1_i, m1_i, s1_i = get_agreement(df_imp_p1)
u3_i, m3_i, s3_i = get_agreement(df_imp_p3)
print(f"P1 Agreement: {u1_i} Unanimous, {m1_i} Majority, {s1_i} Split")
print(f"P3 Agreement: {u3_i} Unanimous, {m3_i} Majority, {s3_i} Split")
acc_imp_p1 = get_accuracy(df_imp_p1)
print(f"P1 Majority Accuracy on these: {acc_imp_p1:.1%}")

# Tiebreaks
# A tiebreak is when P3 max votes < 3. How many such questions?
votes_p3 = df_p3.groupby(['Row_Index', 'Answer']).size().reset_index(name='count')
max_votes_p3 = votes_p3.groupby('Row_Index')['count'].max()
tiebreaks = max_votes_p3[max_votes_p3 < 3].index
print(f"\nNumber of Tiebreaks to Orchestrator: {len(tiebreaks)}")
if len(tiebreaks) > 0:
    df_tiebreaks_p4 = df_p4[df_p4['Row_Index'].isin(tiebreaks)]
    tiebreak_acc = (df_tiebreaks_p4['Answer'] == df_tiebreaks_p4['Correct_Answer']).mean()
    print(f"Orchestrator Tiebreak Accuracy: {tiebreak_acc:.1%}")

