# Design QA — mobile aspect ratio and overflow

## Evidence

- User references: two 1080 × 2351 mobile screenshots supplied in the task. They contain visible personal watermarks and are intentionally excluded from the public repository.
- Implementation captures:
  - `qa/implementation-q4-320x568.png` and `qa/implementation-q4-430x760.png`.
  - `qa/implementation-q6-320x568.png` and `qa/implementation-q6-430x760.png`.
- Side-by-side visual comparison was completed locally; its composite is intentionally not retained because it reproduces the watermarked source screenshots.

The source screenshots include phone and WeChat browser chrome. The implementation captures contain only the app viewport, so the comparison evaluates the app-owned canvas, typography, options and controls rather than the surrounding system UI.

## Root cause and correction

1. P1 — the previous mobile rule independently stretched the 426 × 923 canvas to both viewport width and height. On short screens this compressed the vertical axis, so the mascot looked wider than the source artwork.
2. P1 — the same vertical compression reduced the title/options region. The long Q6 title and fifth price option collided with neighboring regions, while navigation clicks could also leave the document scrolled away from y=0.
3. Fix — the canvas now scales uniformly from viewport width at its original 426:923 ratio, then centers vertically with controlled top/bottom crop. The reward canvas keeps its original 852:1847 ratio by the same rule.
4. Fix — answer space is limited to 45% of the canvas, navigation is anchored to the visible viewport, and each render resets body/document scroll.
5. Fix — at screens no larger than 360 × 700, Q6 uses five 52 px option cards with 6 px gaps so all options clear both the options boundary and navigation controls.

## Required fidelity surfaces

- Image fidelity: original moody mascot and gift artwork are retained and scale uniformly; no horizontal or vertical distortion remains.
- Typography: existing brand fonts, orange hierarchy and brown body text remain unchanged. Q4 and Q6 titles stay inside the outlined title area.
- Layout rhythm: counter → question → hint → options → actions remains ordered with no collision.
- Interaction: selected states, previous/next controls and disabled next state remain functional. Mobile buttons now have real CSS backgrounds because the original baked button artwork can sit outside the cropped canvas on short screens.
- Overflow: document horizontal overflow is 0 at both verification widths. Body and document scroll positions return to 0 after navigation.

## Measured verification

- 320 × 568, Q6: five visible option cards are 52 px high; the final card ends at y=504.9, inside the options boundary y=518.3 and before actions y=523.4. Horizontal overflow=0.
- 430 × 760, Q6: final card ends at y=605.1, inside options boundary y=694.9 and before actions y=700.3. Horizontal overflow=0.
- 430 × 760, Q4: all three cards end by y=471.1, inside options boundary y=694.9. Mascot aspect ratio matches the source asset.

## Interaction and runtime verification

- Replayed the short route: Q1 → Q2 → “只戴美瞳” → Q4 → Q5 → Q6.
- Checked Q4 and Q6 at 320 × 568 and 430 × 760 in the in-app browser.
- No content leaves the canvas and no option is hidden behind navigation.
- Automated Python and Node suites are recorded after the final visual pass.

final result: passed
