# Design QA

- Source visual truth:
  - `C:\Users\Admini\AppData\Local\Temp\codex-clipboard-4445e3b1-af30-4068-ba7d-272538ab53da.jpg`
  - `C:\Users\Admini\AppData\Local\Temp\codex-clipboard-874f53e5-b579-4830-b53a-d0cb2790002e.jpg`
- Browser-rendered implementation evidence:
  - `E:\问卷调查 新内容\survey-app\qa-q7-path1-mobile.png`
  - `E:\问卷调查 新内容\survey-app\qa-q7-path2-mobile.png`
  - `E:\问卷调查 新内容\survey-app\qa-q12-other-mobile.png`
- Source pixels: 838 × 1066 and 920 × 540.
- Implementation pixels / CSS viewport: 390 × 844 at device scale 1.
- State: Question 7 path 1; Question 7 path 2; Question 12 with “其他” selected and a 100-character value.
- Comparison method: both supplied source screenshots and all three browser captures were opened together in the same visual comparison input. The source defines content and control requirements; the existing moody survey defines the visual system.

## Full-view comparison evidence

- Question 7 path 1 contains only the three products shown in the source: M 系列、薄润系列、S 系列. All three cards fit in the mobile content region without scrolling or overlapping the bottom controls.
- Question 7 path 2 contains the three newly specified motivations in the same order as the source. Eight total choices use the existing survey card pattern and an internal vertical scroller; the page itself does not overflow horizontally.
- Question 12 contains “其他”. Selecting it reveals an on-brand text field with an explicit 100-character count. At 390 × 844, the field remains above the persistent action buttons.

## Focused comparison evidence

- Copy was checked directly against the red-boxed text in the Question 7 source and against the “其他” row in the Question 12 source.
- Control behavior was checked at the focused field level: `maxlength=100`, live count `100/100`, forced truncation after a 105-character automated fill, required non-empty text, and server-side truncation/validation.

## Required fidelity surfaces

- Fonts and typography: existing Gotham / Noto Sans SC hierarchy is preserved. The lightweight Noto Sans SC subsets were regenerated to include the new copy.
- Spacing and layout rhythm: all three path-1 cards fit without scroll; long path-2 copy wraps inside cards; the Question 12 field and actions do not collide.
- Colors and visual tokens: existing orange selection, borders, focus ring, cream cards, and counter colors are reused.
- Image quality and asset fidelity: supplied product assets remain unchanged and render sharply with `object-fit: contain`; no placeholder or generated replacement was introduced.
- Copy and content: the three new purchase motivations and Question 12 “其他” match the supplied references.

## Comparison history

1. Initial interaction check found that an automated fill could momentarily produce `105/100`, even though the HTML maxlength and Next-button validation prevented submission.
2. Fix: the input handler now truncates immediately to 100 characters in addition to the HTML and server limits.
3. Post-fix evidence: browser state reports value length 100, `maxlength` 100, count `100/100`, and no console warnings or errors.

## Findings

- No actionable P0, P1, or P2 mismatch remains.
- Expected difference: the source is a plain document screenshot, while the implementation intentionally retains the established moody branded survey shell.

## Primary interactions tested

- Path 1 routing and exactly three product choices.
- Path 2 routing, all eight choices, and maximum-three selection feedback.
- Question 12 Other selection, field reveal, 100-character clamp, live counter, and action-button spacing.
- Six server/API test cases, including empty Other text and server-side 100-character enforcement.
- Browser console warnings/errors: none.

## Follow-up polish

- None required for this content update.

final result: passed
