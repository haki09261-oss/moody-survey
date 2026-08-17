# Design QA — mobile viewport proportion

## Evidence

- Source visual truth: `qa/source-reward-proportion.jpg`
- Source pixels: 945 × 2048. The phone-browser content region is approximately y=142…1809; it was normalized to a 430 × 760 comparison frame by scaling to 430 px wide and removing browser chrome.
- Implementation screenshots:
  - `qa/implementation-reward-430x760.png` — 430 × 760 CSS px, device scale factor 1.
  - `qa/implementation-reward-320x568.png` — 320 × 568 CSS px, device scale factor 1.
- Side-by-side evidence: `qa/comparison-reward-proportion.png` — 920 × 800 px.
- Comparison scaffold: `qa/compare.html`.
- State: valid short-path submission, M 系列 2 片装, 800 度, issued redemption code.

## Full-view comparison

The reference establishes the requested behavior: the survey canvas fills the available phone width and also fits the visible browser height, with no narrow centered canvas or side gutters. The revised implementation follows that behavior at 430 × 760 and 320 × 568. The canvas fills x=0…viewport width and y=0…viewport height, with zero document overflow.

The reference contains phone/browser chrome and a red review annotation. Those are excluded from the app-owned target. The implementation intentionally preserves a little more breathing room above the brand header so the mascot is not clipped by the safe area.

## Focused-region comparison

The reward code, redeem button, and instructions were checked separately because they are the most sensitive to vertical compression. At 320 × 568, 375 × 667, 390 × 844, and 430 × 932:

- reward code remains on one line and inside the viewport;
- redeem button remains fully visible;
- instructions remain inside the canvas;
- horizontal and vertical document overflow both remain zero.

## Required fidelity surfaces

- Fonts and typography: existing Gotham and Noto Sans SC brand fonts are preserved. Code hierarchy, heading weight, and short copy remain legible at the smallest tested width. Dynamic prize/code content changes from the reference are expected data differences.
- Spacing and layout rhythm: the former centered 426:923 contain behavior created visible side gutters at 430 × 760. The revised canvas now occupies the complete safe viewport, matching the reference density. Main card, CTA, and instruction panel remain vertically ordered without overlap.
- Colors and visual tokens: existing moody cream/orange/brown tokens are unchanged and match the source direction.
- Image quality and asset fidelity: supplied moody logo, mascots, frame, gifts, and reward background are retained; no placeholder or generated replacement assets were introduced.
- Copy and content: live prize specification, degree, and redemption code remain dynamic. The shorter instructions are intentional so the smallest screen keeps the same hierarchy without wrapping collisions.

## Comparison history

1. Earlier finding — P2: at 430 × 760 the strict aspect-ratio contain rule rendered the app at roughly 350 px wide, leaving large side gutters and making the experience visibly smaller than the supplied ending-page reference.
2. Fix: changed both questionnaire and reward mobile canvases to use the full safe viewport width and height while preserving the existing percentage-based composition and 100% background fitting.
3. Post-fix evidence: `qa/comparison-reward-proportion.png`, plus the 320 × 568 and 430 × 760 implementation captures. No actionable P0/P1/P2 mismatch remains for the requested proportion.

## Interaction and runtime verification

- Completed the short questionnaire route from question 1 through degree selection and submission.
- Confirmed a valid reward code was generated and rendered.
- Checked console error logs on the questionnaire/reward page and comparison page: no errors.
- Responsive matrix: 320 × 568, 375 × 667, 390 × 844, 430 × 932.

## Follow-up polish

- P3: the reference places its header slightly higher because its top is cropped by browser chrome. The implementation keeps the full mascot visible; this is an intentional safe-area improvement.

final result: passed
