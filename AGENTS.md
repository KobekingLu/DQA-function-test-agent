# AGENTS.md

## Project / 專案名稱
DQA Function Test Review Agent

## Project Goal / 專案目標
這個 folder 是從目前的 ES Tracking / pre-shipment demo 延伸出來的平行 prototype。

目標是做出一個可執行、可展示的 AI agent demo，協助 DQA 在 function 測試流程中：
- 盤點 test plan
- 讀取 actual execution result
- 對照 known issues
- 找出 failure、blocked item、missing evidence
- 評估 release / exit 風險
- 建議下一步 action 與 owner

---

## Current Stage / 目前階段
這個 folder 目前是 version-1 demo scaffold。

優先順序：
1. keep the demo runnable
2. keep the output demo-friendly
3. keep the logic easy to modify
4. gradually move from fake case to real DQA evidence

請不要 over-engineer。

---

## Current Working Mode / 目前工作模式
目前先以 Demo Scenario Mode 為主。

Agent 會：
1. load expected test plan
2. load actual execution result
3. load known issue list
4. compare expected vs actual coverage and status
5. evaluate function-test risk
6. render JSON and bilingual HTML review result

---

## Current Output / 目前輸出
目前應維持以下輸出能力：

- JSON analysis outputs
- bilingual HTML overview page
- bilingual HTML detail pages
- support for:
  - Ready for Exit
  - Retest Required
  - Block Release

HTML output 應幫助解釋：
- what the agent reviewed
- which tests passed or failed
- where evidence is missing
- why the recommendation was made
- who should handle next action

---

## Input Data / 輸入資料
### Current input folders
- `demo_cases/` -> fake DQA function-test cases

### Demo case inputs may include
- `expected_tests.csv`
- `actual_results.csv`
- `known_issues.csv`

Version 1 可接受：
- simplified field definitions
- partial parsing
- fake data 補 demo 情境
- manual mapping

---

## HTML Presentation Rules / HTML 呈現原則
1. 保持 overview + detail page 結構
2. 保持 bilingual style（English + Traditional Chinese）
3. section titles 應維持雙語
4. key summary text 應維持雙語
5. technical details 可主要保留英文
6. 不要讓頁面過度擁擠
7. 保持「像 AI Agent workflow demo」的語氣

建議保留 agent wording：
- agent inspected
- agent matched
- agent detected
- agent found missing evidence
- agent recommended retest
- agent recommended release stop

---

## Practical Development Rules / 實作原則
- 使用 Python
- 模組保持小而實用
- 優先 readable code，不要過度抽象
- 盡量沿用目前 pre-shipment demo 的資料節奏
- version 1 先以規則式 decision logic 為主
- 新功能優先增量加入，不要推翻已可展示的流程

---

## Suggested Files / 建議檔案結構
- `AGENTS.md`
- `README.md`
- `NEXT_STEP.md`
- `demo_cases/`
- `output/`
- `demo.py`
- package code for parser / decision / rendering

---

## Next Direction / 下一步方向
下一階段可優先思考：

1. 如何讓 agent 讀 real DQA test plan
2. 如何讀實際的 test execution log / CSV / report
3. 如何串 defect list / waiver list
4. 如何產生 explainable test exit review
5. 如何保留目前 bilingual HTML demo 優勢

---

## Important Notes / 重要提醒
- 第一優先是 demo 可展示、可錄影
- fake demo cases 是正式 demo 的一部分，不是垃圾資料
- 若 evidence 不足，agent 應明確指出 missing coverage
- output 要幫助 DQA / RD / PM 快速理解風險與 next action

---

## When Unsure / 不確定時
如果遇到欄位不一致或資料不足：

1. 先列出觀察到的結構
2. 提出合理 mapping
3. 用最小假設先讓 demo 可跑
4. 保留既有 JSON / HTML output structure
5. 不要輕易破壞 bilingual demo 能力
