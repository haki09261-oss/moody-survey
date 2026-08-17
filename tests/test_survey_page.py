# tests/test_survey_page.py
import zlib

import pytest

from app.models import Survey


@pytest.fixture
def survey(db_session):
    s = Survey(slug="spring", title="春季问卷", schema_json=[])
    db_session.add(s)
    db_session.commit()
    return s


def test_survey_page_served(client, survey):
    resp = client.get("/s/spring")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "survey.js" in resp.text


def test_survey_page_does_not_serve_path_channel_links(client, survey):
    resp = client.get("/s/spring/ch/tmall")
    assert resp.status_code == 404


def test_survey_page_references_background_artwork(client, survey):
    resp = client.get("/s/spring")
    assert resp.status_code == 200
    assert "survey-question-bg.webp" in resp.text
    assert "reward-page-clean.webp" in resp.text
    assert "page-question" in resp.text
    assert "page-result" in resp.text


def test_survey_page_configures_file_preview_assets(client, survey):
    resp = client.get("/s/spring")
    assert resp.status_code == 200
    assert "location.protocol === \"file:\"" in resp.text
    assert "--question-bg" in resp.text
    assert "--result-bg" in resp.text
    assert "--question-bg: url(\"/static/survey-question-bg.webp?v=1\")" in resp.text


def test_survey_page_cache_busts_dynamic_script(client, survey):
    resp = client.get("/s/spring")
    assert resp.status_code == 200
    assert '"/static/survey.js?v=' in resp.text
    assert '"/static/survey.js?v=current6"' in resp.text
    assert '"/static/survey.js?v=tmall2"' not in resp.text
    assert '"/static/survey.js?v=tmall1"' not in resp.text
    assert '"/static/survey.js?v=fit34"' not in resp.text
    # 改动 survey.js 后版本号必须同步 bump，否则手机 WebView 命中旧缓存
    assert '"/static/survey.js?v=swipe17"' not in resp.text
    # HTML 本身禁缓存（每次回源校验），防止缓存的旧 HTML 继续引用旧 v= 脚本
    assert resp.headers.get("cache-control") == "no-cache"


def test_survey_tier1_uses_answer_driven_reward_route(client, survey):
    html = client.get("/s/spring")
    assert html.status_code == 200
    js = client.get("/static/survey.js")
    assert js.status_code == 200
    assert "function completeTier1ByRoute" in js.text
    assert "stepAnswers.q3 === ONLY_BEAUTY" in js.text
    assert "submitTier1Only()" in js.text
    assert "submitTier1AndContinue()" in js.text


def test_survey_page_uses_artwork_canvas_layout(client, survey):
    resp = client.get("/s/spring")
    assert resp.status_code == 200
    assert "aspect-ratio: 941 / 1672" in resp.text
    # 画布同时受屏宽与屏高约束（contain），宽屏/折叠屏（如 Pura X）不再竖向溢出
    assert "--canvas-width: min(100vw, calc(100vh * 941 / 1672), 640px)" in resp.text
    # 画布内文字尺寸跟画布宽走（--cw = 画布宽 1%），宽屏/折叠屏上不再按视口 vw 放大
    assert "--cw: calc(var(--canvas-width) / 100)" in resp.text
    # 现代浏览器用 svh 增强，消除地址栏伸缩导致的溢出；老 WebView 回退 vh
    assert "calc(100svh * 941 / 1672)" in resp.text
    assert ".wrap { width: var(--canvas-width)" in resp.text
    assert "height: calc(var(--canvas-width) * 1672 / 941)" in resp.text
    assert ".wrap.is-extended-artwork" in resp.text
    assert "background-image: var(--question-bg)" in resp.text
    assert "body.page-result .wrap" in resp.text
    assert ".sheet { position: absolute" in resp.text
    assert "background: transparent" in resp.text
    assert "body.page-result .sheet" in resp.text
    assert ".q-block { position: absolute" in resp.text
    assert "min-height: 500px" in resp.text
    assert ".q-block::before { display: none" in resp.text
    assert ".code-box { position: absolute; z-index: 2; left: 15.8%; top: 45.4%" in resp.text
    assert ".activity-note" not in resp.text


def test_survey_page_positions_dynamic_content_inside_artwork_slots(client, survey):
    resp = client.get("/s/spring")
    assert resp.status_code == 200
    assert "--question-left: 40.4%" in resp.text
    assert "--question-top: 19.8%" in resp.text
    assert "--question-width: 43.8%" in resp.text
    assert "--options-left: 13.6%" in resp.text
    assert "--options-top: 41.4%" in resp.text
    assert "--options-width: 79.2%" in resp.text
    assert "position: absolute; left: var(--question-left)" in resp.text
    assert ".art-options { position: absolute" in resp.text
    assert "grid-template-rows: repeat(var(--option-count), var(--option-row-height" in resp.text
    assert "align-content: start" in resp.text
    # 滑动提示文本已移除（保留两侧箭头）
    assert "swipeHint" not in resp.text
    assert "左滑下一题" not in resp.text
    # 选项列按最长选项自适应居中
    assert ".art-options.art-choices { left: 50%; transform: translateX(-50%); width: fit-content" in resp.text


def test_survey_page_renders_side_swipe_arrows_and_motion_styles(client, survey):
    resp = client.get("/s/spring")
    assert resp.status_code == 200
    assert "swipe-side-hints" in resp.text
    assert "swipe-side-arrow swipe-side-left" in resp.text
    assert "swipe-side-arrow swipe-side-right" in resp.text
    assert 'id="swipeSideLeft"' in resp.text
    assert 'id="swipeSideRight"' in resp.text
    assert 'type="button"' in resp.text
    assert "aria-label=\"返回上一题\"" in resp.text
    assert "aria-label=\"下一题\"" in resp.text
    assert "‹" in resp.text
    assert "›" in resp.text
    assert "swipe-arrow swipe-arrow-left" not in resp.text
    assert "swipe-arrow swipe-arrow-right" not in resp.text
    assert "pointer-events: auto" in resp.text
    assert "color: var(--art-orange-deep)" in resp.text
    assert "background: rgba(255,106,34,.12)" in resp.text
    assert "@keyframes swipeSidePulseLeft" in resp.text
    assert "@keyframes swipeSidePulseRight" in resp.text
    assert ".q-block.is-slide-enter-next" in resp.text
    assert ".q-block.is-slide-leave-prev" in resp.text
    assert "transition: transform .28s ease, opacity .28s ease" in resp.text


def test_survey_page_matches_artwork_typography(client, survey):
    resp = client.get("/s/spring")
    assert resp.status_code == 200
    assert "--art-orange: #ff6a22" in resp.text
    assert "--art-orange-deep: #ff4f14" in resp.text
    assert "--art-brown: #5b3826" in resp.text
    assert "color: var(--art-orange)" in resp.text
    assert "font-size: clamp(15px, calc(var(--cw) * 3.8), 22px)" in resp.text
    assert "font-weight: 700" in resp.text
    assert "text-shadow: 0 1px 0 rgba(255,255,255,.55)" in resp.text
    assert ".art-choices > label" in resp.text
    assert "color: var(--art-brown)" in resp.text
    assert "font-size: clamp(12px, calc(var(--cw) * 3.1), 16px)" in resp.text
    assert "font-weight: 600" in resp.text
    assert "background: transparent; border: 0; box-shadow: none" in resp.text
    assert ".art-choices::before" in resp.text
    assert "content: \"\"; position: absolute; inset: 0; display: block" in resp.text
    assert "background: radial-gradient(ellipse at center, rgba(255,246,234,.66) 0%, rgba(255,238,221,.46) 58%, rgba(255,228,205,.22) 78%, rgba(255,246,236,0) 100%)" in resp.text
    assert "border: 0;" in resp.text
    assert "box-shadow: inset 0 0 42px rgba(255,255,255,.26), 0 0 24px rgba(255,225,190,.18)" in resp.text
    assert "linear-gradient(180deg, rgba(255,241,222,.92), rgba(255,232,207,.88))" not in resp.text
    assert "rgba(255,239,222,.94)" not in resp.text
    assert "rgba(255,132,48,.58)" not in resp.text
    assert "display: flex; flex-direction: column; justify-content: flex-start" in resp.text
    assert "overflow-y: hidden" in resp.text
    assert "scrollbar-width: none" in resp.text
    assert ".art-choices > .other-input" in resp.text
    assert "width: auto; height: max(24px, calc(var(--option-row-height, 44px) - 4px)); min-height: 0" in resp.text
    assert "min-width: clamp(220px, calc(var(--cw) * 45), 320px); max-width: calc(var(--canvas-width) * .62)" in resp.text
    assert "margin: 0 clamp(13px, calc(var(--cw) * 3.1), 20px); align-self: stretch" in resp.text
    assert "background: rgba(255,246,235,.74)" in resp.text
    assert "border: 1px solid rgba(255,138,61,.22)" in resp.text
    assert "background: rgba(255,251,244,.48)" not in resp.text
    assert "border: 1px solid rgba(255,183,128,.58)" not in resp.text
    assert "border-color: var(--art-orange)" in resp.text


def test_survey_page_lets_result_artwork_own_code_box_and_redeem_button(client, survey):
    resp = client.get("/s/spring")
    assert resp.status_code == 200
    assert "--result-bg: url(\"/static/reward-page-clean.webp?v=1\")" in resp.text
    assert "#result { position: absolute; inset: 0; width: 100%; height: 100%" in resp.text
    assert ".code-box { position: absolute; z-index: 2; left: 15.8%; top: 45.4%" in resp.text
    assert "background: transparent; border: 0; box-shadow: none" in resp.text
    assert ".code { display: block; width: 100%; max-width: 100%; min-width: 0" in resp.text
    assert "overflow: hidden; text-align: center" in resp.text
    assert "font-size: clamp(16px, calc(var(--cw) * 4.8), 27px); font-weight: 800; letter-spacing: 0" in resp.text
    assert "#newProductWrap { position: absolute; left: 12.6%; right: 12.6%; top: 56.25%; height: 5.55%" in resp.text
    assert "#newProductBtn { width: 100%; height: 100%; min-height: 0; padding: 0; border: 0" in resp.text
    assert "background: transparent; color: #fff; box-shadow: none" in resp.text


def test_survey_page_keeps_artwork_aligned_without_horizontal_overflow(client, survey):
    resp = client.get("/s/spring")
    assert resp.status_code == 200
    assert "html, body { overflow-x: hidden" in resp.text
    assert ".art-choices > label:has(input[type=radio])::before { border-radius: 6px" in resp.text
    assert ".art-choices > label:has(input[type=radio]:checked)::after { content: \"✓\"" in resp.text


def test_survey_page_styles_scale_questions_as_light_artwork_controls(client, survey):
    resp = client.get("/s/spring")
    assert resp.status_code == 200
    assert ".art-inputs:has(.scale-row)" in resp.text
    assert "grid-template-columns: repeat(6, minmax(0, 1fr))" in resp.text
    assert "height: clamp(30px, calc(var(--cw) * 7.4), 44px)" in resp.text
    assert "font-size: clamp(12px, calc(var(--cw) * 3.1), 16px)" in resp.text


def _png_rgba(data):
    offset = 8
    width = height = color_type = 0
    idat = []
    while offset < len(data):
        length = int.from_bytes(data[offset:offset + 4], "big")
        offset += 4
        chunk_type = data[offset:offset + 4]
        offset += 4
        payload = data[offset:offset + length]
        offset += length + 4
        if chunk_type == b"IHDR":
            width = int.from_bytes(payload[0:4], "big")
            height = int.from_bytes(payload[4:8], "big")
            color_type = payload[9]
        elif chunk_type == b"IDAT":
            idat.append(payload)
        elif chunk_type == b"IEND":
            break

    channels = 4 if color_type == 6 else 3
    stride = width * channels
    raw = zlib.decompress(b"".join(idat))
    rows = []
    pos = 0
    prev = [0] * stride
    for _ in range(height):
        filter_type = raw[pos]
        pos += 1
        row = list(raw[pos:pos + stride])
        pos += stride
        for i, value in enumerate(row):
            left = row[i - channels] if i >= channels else 0
            up = prev[i]
            up_left = prev[i - channels] if i >= channels else 0
            if filter_type == 1:
                row[i] = (value + left) & 255
            elif filter_type == 2:
                row[i] = (value + up) & 255
            elif filter_type == 3:
                row[i] = (value + ((left + up) // 2)) & 255
            elif filter_type == 4:
                p = left + up - up_left
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - up_left)
                predict = left if pa <= pb and pa <= pc else (up if pb <= pc else up_left)
                row[i] = (value + predict) & 255
        rows.append(row)
        prev = row
    return width, rows, channels


def _png_pixel(image, x, y):
    width, rows, channels = image
    start = x * channels
    return rows[y][start:start + channels]


def _count_option_box_trace_pixels(image):
    width, rows, channels = image
    count = 0
    for y in range(690, 1500):
      row = rows[y]
      for x in range(120, 870):
          start = x * channels
          r, g, b = row[start:start + 3]
          if r <= 251 and g <= 241 and b <= 230 and r - g < 18:
              count += 1
    return count


def _count_pixels(image, x0, y0, x1, y1, predicate):
    width, rows, channels = image
    count = 0
    for y in range(y0, y1):
        row = rows[y]
        for x in range(x0, x1):
            start = x * channels
            if predicate(row[start:start + 3]):
                count += 1
    return count


def test_question_artwork_uses_clean_template_without_checkbox_boxes(client, survey):
    resp = client.get("/static/survey-question-bg.png")
    assert resp.status_code == 200
    image = _png_rgba(resp.content)
    assert _count_option_box_trace_pixels(image) < 5000


def test_result_artwork_uses_current_clean_webp(client, survey):
    resp = client.get("/static/reward-page-clean.webp")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/webp"
    assert resp.content.startswith(b"RIFF") and b"WEBP" in resp.content[:16]


def test_survey_page_embeds_text_without_floating_boxes(client, survey):
    resp = client.get("/s/spring")
    assert resp.status_code == 200
    assert ".q-title { position: absolute" in resp.text
    assert "background: transparent; border: 0; border-radius: 0" in resp.text
    assert ".art-choices > label" in resp.text
    assert "background: transparent; border: 0; box-shadow: none" in resp.text
    assert ".art-choices > label::before" in resp.text
    assert ".art-choices > label > input[type=radio]" in resp.text
    assert "opacity: 0; pointer-events: none" in resp.text
    assert ".art-inputs > input[type=text]" in resp.text


def test_survey_script_has_file_preview_guard(client):
    resp = client.get("/static/survey.js")
    assert resp.status_code == 200
    assert "location.protocol === \"file:\"" in resp.text
    assert "当前是文件预览模式" in resp.text


def test_survey_script_builds_adaptive_artwork_slots(client):
    resp = client.get("/static/survey.js")
    assert resp.status_code == 200
    assert "art-options" in resp.text
    assert "art-choices" in resp.text
    assert "art-inputs" in resp.text
    assert "--option-count" in resp.text
    assert "--option-slot-count" in resp.text
    assert "--option-row-height" in resp.text
    assert "--options-render-height" in resp.text
    assert "is-long-list" in resp.text
    assert "visibleArtworkChoiceRows" in resp.text
    assert "display !== \"none\"" in resp.text
    assert "compactChoiceGap" in resp.text
    assert "fitChoiceRowsInsideArtwork" in resp.text
    assert "box.scrollTop = 0" in resp.text
    assert "layoutSlotCount" in resp.text
    assert "layoutSlotCount = Math.max(slotCount, rowCount)" in resp.text
    assert "Math.min(slotCount, 8)" not in resp.text
    assert "submitWrap.style.top" in resp.text
    assert 'box.classList.contains("art-choices")' in resp.text
    assert "fitTitleToSlot" in resp.text
    assert "fitArtworkText" in resp.text


def test_survey_script_does_not_compress_choice_text(client):
    resp = client.get("/static/survey.js")
    assert resp.status_code == 200
    assert "choice-text" in resp.text
    assert "fitTitleToSlot" in resp.text
    # 量测兜底：折行文本装不下行高 → 先缩字号、仍不行加高行并延伸渲染高度（防选项叠压，Pura X 等窄画布）
    assert "tallestChoiceTextHeight" in resp.text
    assert "shrinkChoiceFontUntilFit" in resp.text
    assert "label.scrollHeight" in resp.text
    assert "grownRenderHeight" in resp.text
    assert "fitTextToSlot(label" not in resp.text


def test_survey_script_reserves_space_for_step_navigation_buttons(client):
    resp = client.get("/static/survey.js")
    assert resp.status_code == 200
    assert "reserveArtworkBottomSpace" in resp.text
    assert "artworkNaturalHeight" in resp.text
    assert "measuredOptionsBottomFromWrap" in resp.text
    assert "scheduleSubmitPosition" in resp.text
    assert "settleArtworkLayout" in resp.text
    assert "getBoundingClientRect" in resp.text
    assert "submitWrap.offsetHeight" in resp.text
    assert "wrap.style.minHeight" in resp.text


def test_survey_script_uses_swipe_navigation_instead_of_step_buttons(client):
    resp = client.get("/static/survey.js")
    assert resp.status_code == 200
    assert "attachSwipeNavigation" in resp.text
    assert "handleSwipeNavigation" in resp.text
    assert "touchstart" in resp.text
    assert "pointerdown" in resp.text
    assert 'mkButton("上一题"' not in resp.text
    assert 'mkButton("下一题"' not in resp.text


def test_survey_script_animates_step_changes_by_direction(client):
    resp = client.get("/static/survey.js")
    assert resp.status_code == 200
    assert "STEP_TRANSITION_MS" in resp.text
    assert "transitionStepBlock" in resp.text
    assert "is-slide-enter-next" in resp.text
    assert "is-slide-leave-next" in resp.text
    assert "is-slide-enter-prev" in resp.text
    assert "is-slide-leave-prev" in resp.text
    assert 'renderStep("next")' in resp.text
    assert 'renderStep("prev")' in resp.text


def test_survey_script_fits_redeem_code_against_parent_slot(client):
    resp = client.get("/static/survey.js")
    assert resp.status_code == 200
    assert "const slotWidth = el.parentElement ? el.parentElement.clientWidth : el.clientWidth" in resp.text
    assert "el.scrollWidth > slotWidth" in resp.text
    assert 'fitSingleLineToSlot(root.querySelector(".code"), 16);' in resp.text


def test_survey_script_clicks_side_arrows_to_navigate(client):
    resp = client.get("/static/survey.js")
    assert resp.status_code == 200
    assert "attachSideArrowNavigation" in resp.text
    assert "swipeSideLeft" in resp.text
    assert "swipeSideRight" in resp.text
    assert 'handleSwipeNavigation("prev")' in resp.text
    assert 'handleSwipeNavigation("next")' in resp.text
    assert 'addEventListener("click"' in resp.text


def test_survey_script_auto_advances_single_choice_on_change(client):
    resp = client.get("/static/survey.js")
    assert resp.status_code == 200
    assert "shouldAutoAdvanceSingleChoice" in resp.text
    assert "maybeAutoAdvanceSingleChoice" in resp.text
    assert 'input.addEventListener("change"' in resp.text


@pytest.mark.parametrize("asset", ["survey-question-bg.png"])
def test_survey_background_artwork_served(client, asset):
    resp = client.get(f"/static/{asset}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_survey_page_renders_degree_modal(client, survey):
    resp = client.get("/s/spring")
    assert resp.status_code == 200
    assert 'id="degreeModal"' in resp.text
    assert 'id="degreeInput"' in resp.text
    assert 'id="degreeDone"' in resp.text
    assert "填写完成" in resp.text
    assert ".degree-modal.is-open" in resp.text


def test_survey_page_embeds_activity_note_inside_result_artwork(client, survey):
    resp = client.get("/s/spring")
    assert resp.status_code == 200
    assert "活动说明" not in resp.text
    assert "仅面向收到 moody 官方邀约" not in resp.text
    assert "body.page-result .wrap .activity-note" not in resp.text
    assert ".activity-note" not in resp.text
    assert '    <div class="activity-note">' not in resp.text


def test_survey_page_renders_rules_floating_button_and_panel(client, survey):
    resp = client.get("/s/spring")
    assert resp.status_code == 200
    assert 'id="rulesFab"' in resp.text
    assert "活动规则" in resp.text
    assert 'id="rulesModal"' in resp.text
    assert 'id="rulesClose"' in resp.text
    assert "问卷链接有效期为72小时" in resp.text
    assert "（以商家后台订单支付时间为准）" in resp.text
    assert "港澳台及海外不发货" in resp.text
    assert "奖品不支持折现或转让，佩戴效果及感受因人而异，发出后非质量问题不支持退换" in resp.text
    assert "最终解释权归 moody 品牌官方所有" in resp.text
    assert ".rules-fab { position: fixed" in resp.text
    assert "top: calc(var(--canvas-width) * 1672 / 941 * .365)" in resp.text
    assert "right: calc((100vw - var(--canvas-width)) / 2 + var(--canvas-width) * .018)" in resp.text
    assert "width: clamp(30px, 7.4vw, 42px)" in resp.text
    assert "height: clamp(44px, 10.6vw, 58px)" in resp.text
    assert "writing-mode: vertical-rl" in resp.text
    assert "background: rgba(91,56,38,.72)" in resp.text
    assert "color: #fff8ee" in resp.text
    assert ".rules-close { width: 30px; height: 30px; padding: 0; border: 0; border-radius: 0" in resp.text
    assert "background: transparent; box-shadow: none" in resp.text


def test_survey_script_collects_degree_via_popup(client):
    resp = client.get("/static/survey.js")
    assert resp.status_code == 200
    assert "function askDegree" in resp.text
    assert "degreeQuestions" in resp.text
    assert "list.filter((q) => q.degree)" in resp.text       # 度数题排除出逐题流程
    assert "const extra = await askDegree();" in resp.text    # 两个最终提交都先弹度数


def test_survey_script_wires_rules_panel(client):
    resp = client.get("/static/survey.js")
    assert resp.status_code == 200
    assert "function attachRulesPanel" in resp.text
    assert "attachRulesPanel();" in resp.text


def test_survey_script_claims_token_and_validates_degree(client):
    resp = client.get("/static/survey.js")
    assert resp.status_code == 200
    # 通用链接 claim：原地换 token 页内重拉，不整页刷新（无白屏/二次底图）
    assert 'token_status === "claim"' in resp.text
    assert 'searchParams.set("t", token)' in resp.text
    assert "location.replace" not in resp.text
    assert "fetchSurveyData" in resp.text
    # 72h 过期文案
    assert "问卷已关闭" in resp.text
    assert "该链接已过期" not in resp.text
    # 度数改为后端 schema 下发的固定规格选项，避免手输不存在的规格。
    assert 'input.innerHTML = \'<option value="">请选择度数</option>\'' in resp.text
    assert "请选择用于兑奖的镜片度数" in resp.text


def test_survey_script_compacts_many_option_rows(client):
    resp = client.get("/static/survey.js")
    assert resp.status_code == 200
    # 多选项题（>8 行）：行高按"提交按钮标准槽位之上"的预算高度算，收进原框
    assert "* 0.885" in resp.text
    # 实际占用高度写回，背景光晕/提交按钮紧跟最后一个选项
    assert "compactUsedHeight" in resp.text


def test_survey_script_locks_canvas_width_against_keyboard_resize(client):
    resp = client.get("/static/survey.js")
    assert resp.status_code == 200
    # Pura X 等 HarmonyOS/Android WebView：键盘弹出会压缩布局视口高度，
    # vh 驱动的画布宽度随之坍缩导致整页挤变形。画布宽度须由 JS 冻结为像素值，
    # 仅视口宽度变化（转屏/折叠）时重算，纯高度变化（键盘）忽略。
    assert "function lockCanvasWidth" in resp.text
    assert 'setProperty("--canvas-width"' in resp.text
    assert "window.innerWidth === lockedViewportWidth" in resp.text


def test_survey_grow_fallback_only_grows_wrapped_rows(client, survey):
    js = client.get("/static/survey.js")
    assert js.status_code == 200
    # 量测兜底：仅折行装不下的行自然加高（flow 模式），不再统一抬高所有行
    assert "art-choices-flow" in js.text
    assert "grownRowHeight" not in js.text
    # 「其他」输入框可见时的底部内边距计入紧凑高度
    assert "paddingBottom" in js.text
    html = client.get("/s/spring")
    assert ".art-choices.art-choices-flow > label { height: auto; min-height: var(--option-row-height" in html.text


def test_survey_fit_ignores_non_label_rows_and_degree_copy(client, survey):
    js = client.get("/static/survey.js")
    # 行高/字号只按选项行(label)计算，「其他」输入框/备注不占槽位 → 勾选后全局不再缩小
    assert 'tagName === "LABEL"' in js.text
    # 度数弹窗提示文案（默认值）
    new_copy = "兑换奖品前需填写镜片度数；若左右眼度数不同，建议填写较低度数；如未填写，默认发放0度镜片。"
    assert new_copy in js.text
    assert "不填默认 0 度" not in js.text
    html = client.get("/s/spring")
    assert new_copy in html.text


def test_survey_fit_is_stable_across_option_checks(client):
    js = client.get("/static/survey.js")
    # 字号/缩字/flow 判定只在签名(行数×画布宽×槽位高)变化时执行一次：
    # 勾选选项触发的重排不得重置字号 → 字体不再跳变
    assert "fitSig" in js.text
    # 「其他」输入框固有宽度钉最小，显形不撑宽 fit-content 列
    assert "ti.size = 1" in js.text


def test_survey_plain_page_uses_dedicated_artwork_with_centered_message(client, survey):
    resp = client.get("/s/spring")
    assert resp.status_code == 200
    # 无资格页使用完整成品底图自带文案；其他 plain 状态仍用空白底图叠加自己的提示
    assert '--plain-bg: url("/static/survey-plain-empty-bg.webp?v=1")' in resp.text
    assert '--plain-ineligible-bg: url("/static/survey-plain-empty-bg.webp?v=1")' in resp.text
    assert "body.page-plain .wrap { background-image: var(--plain-bg); }" in resp.text
    assert "body.page-plain.page-ineligible .wrap { background-image: var(--plain-ineligible-bg); }" in resp.text
    assert "body.page-plain.page-ineligible h1#title { display: block" in resp.text
    js = client.get("/static/survey.js")
    assert js.status_code == 200
    assert '"page-question", "page-result", "page-plain", "page-ineligible"' in js.text
    assert 'showOnlyTitle("无资格", "ineligible")' in js.text


def test_plain_empty_artwork_remains_available_for_generic_plain_pages(client, survey):
    resp = client.get("/static/survey-plain-empty-bg.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    image = _png_rgba(resp.content)
    dark_text = lambda p: p[0] < 125 and p[1] < 100 and p[2] < 90
    orange_text = lambda p: p[0] > 210 and 55 < p[1] < 145 and p[2] < 95
    assert _count_pixels(image, 150, 205, 560, 390, dark_text) < 300
    assert _count_pixels(image, 130, 605, 820, 690, orange_text) < 300


def test_survey_tracking_landing_and_dedup_leave(client):
    js = client.get("/static/survey.js")
    assert js.status_code == 200
    # 页面浏览携带落地页类型
    assert "答题页" in js.text and "无资格页" in js.text and "兑奖码页" in js.text
    assert 'track("page_view", { value: landing })' in js.text
    # 页面离开去重：每次真实离开只记一条,带流失题目与累计停留
    assert "leaveSent" in js.text
    assert "function trackLeave()" in js.text


def test_survey_tracks_degree_modal_and_redeem_code(client):
    js = client.get("/static/survey.js")
    assert js.status_code == 200
    # 度数弹窗：弹出/完成各一条(完成带填写值,未填记"未填")
    assert 'track("degree_view"' in js.text
    assert 'track("degree_done"' in js.text
    assert '"未填"' in js.text
    # 去兑奖点击带兑换码内容
    assert 'track("redeem_click", { value: code || "无码", dwell_ms: Date.now() - shownAt })' in js.text


def test_survey_degree_and_redeem_carry_dwell(client):
    js = client.get("/static/survey.js")
    assert js.status_code == 200
    # 填写度数=度数框弹出到完成的耗时;点击去兑奖=看码页到点击的耗时
    assert "degreeOpenedAt" in js.text
    assert 'dwell_ms: Date.now() - degreeOpenedAt' in js.text
    assert 'dwell_ms: Date.now() - shownAt' in js.text


def test_survey_resumes_tier2_after_reopen(client):
    js = client.get("/static/survey.js")
    assert js.status_code == 200
    # 已提交但只到 Tier1 且有进阶题 → 重进续答进阶,不锁死兑奖码页
    assert "const resumeTier2 = " in js.text
    assert 'data.submitted_tier === 1 && tier2.length > 0' in js.text
    assert "if (resumeTier2) { startTier2(); return; }" in js.text
    assert "答题页(进阶续答)" in js.text


def test_survey_script_passes_aid_and_miniapp_flag(client):
    js = client.get("/static/survey.js")
    assert js.status_code == 200
    # 读取 aid / mp 两个 query
    assert 'params.get("aid")' in js.text
    assert 'params.get("mp")' in js.text
    # claim 请求带 aid
    assert "&aid=" in js.text


def test_survey_script_redeem_uses_postmessage_in_miniapp(client):
    js = client.get("/static/survey.js")
    assert js.status_code == 200
    # 小程序内：去兑奖走淘系 web-view 桥 postMessage，不直接 location.href 跳 tmall
    assert "my.postMessage" in js.text
    assert '"open_product"' in js.text
    # 非小程序仍保留原 window.open 回退
    assert 'window.open(newProductUrl, "_blank")' in js.text


def test_survey_page_injects_miniapp_webview_bridge(client, survey):
    resp = client.get("/s/spring")
    assert resp.status_code == 200
    # mp=1 时注入淘系 web-view 桥（手淘内才可用）
    assert "https://appx/web-view.min.js" in resp.text
    assert 'params.get("mp")' in resp.text  # 注入受 mp=1 控制
