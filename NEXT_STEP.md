# NEXT_STEP.md

## Current Status
This folder already has a runnable demo scaffold for DQA function-test review.

### Completed
- fake demo case support
- rule-based function-test decision logic
- JSON outputs
- bilingual HTML overview page
- bilingual HTML detail pages
- three demo outcomes:
  - Ready for Exit
  - Retest Required
  - Block Release

## Next Main Goal
Move from fake demo cases to real DQA workflow inputs:

1. real test plan source
2. real execution log or test result export
3. real bug / waiver / known issue list
4. explainable test exit review output

## Practical Next Steps
1. Define one target product or feature area
2. Normalize a small real test plan
3. Normalize one actual execution report
4. Define how waiver / known issue status should affect decision
5. Keep the bilingual HTML output demo-friendly

## Handoff Prompt
Use this when continuing work in this folder:

This folder is DQA Function Test Review Agent.

Please first read:
- dqa_function_agent/AGENTS.md
- dqa_function_agent/README.md
- dqa_function_agent/NEXT_STEP.md

Then inspect the folder and summarize:
- what is already completed
- what the current demo can show
- what the next main implementation goal should be
