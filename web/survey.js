// web/survey.js
(function () {
  const params = new URLSearchParams(location.search);
  const slug = location.pathname.split("/").pop();
  const channel = params.get("c") || "unknown";
  const aid = params.get("aid") || "";
  const isMiniapp = params.get("mp") === "1";
  let token = params.get("t") || null;   // claim 后原地更新，不整页刷新
  const isFilePreview = location.protocol === "file:";
  const startedAt = Date.now();
  const ONLY_BEAUTY = "只戴美瞳";
  let fingerprint = "";
  let schema = [];
  let tier1 = [];
  let tier2 = [];
  let degreeQuestions = [];   // 度数题（degree:true）不进逐题流程，改由提交后弹窗收集
  let questionEnteredAt = 0;  // 当前题进入时刻，翻题时算出停留时长上报

  function questionDwellMs() {
    return questionEnteredAt ? Date.now() - questionEnteredAt : 0;
  }
  let newProductUrl = "";

  // ===== 埋点 tracker（缓冲批量 + 离开 beacon）=====
  const sessionId = "s-" + startedAt.toString(36) + "-" + Math.random().toString(36).slice(2, 8);
  let eventQueue = [];
  let flushTimer = null;
  const FILE_PREVIEW_SCHEMA = [
    {
      id: "q_preview_focus",
      type: "multi",
      tier: 1,
      title: "选购 moody 美瞳时，您最看重以下哪些因素？",
      options: [
        "颜色 / 花色自然度",
        "佩戴舒适度",
        "直径 / 放大效果",
        "含水量 / 水润感",
        "价格",
        "品牌口碑",
        "包装颜值",
        "度数是否齐全",
      ],
    },
    {
      id: "q_preview_style",
      type: "single",
      tier: 1,
      title: "您更偏好的美瞳风格是？",
      options: ["自然日常", "甜美灵动", "混血感", "个性显色"],
    },
    {
      id: "q_preview_cycle",
      type: "single",
      tier: 1,
      title: "您通常选择什么抛期？",
      options: ["日抛", "月抛", "半年抛", "年抛"],
    },
    {
      id: "q_preview_scene",
      type: "multi",
      tier: 1,
      title: "您主要在哪些场景佩戴美瞳？",
      options: ["日常通勤", "约会聚会", "拍照出游", "上班上学"],
    },
    {
      id: "q_preview_wish",
      type: "multi",
      tier: 1,
      title: "您希望 moody 后续优化哪些体验？",
      options: ["更多花色", "更多度数", "更多优惠", "更快上新"],
    },
    {
      id: "q_preview_degree",
      type: "text",
      tier: 1,
      optional: true,
      degree: true,
      title: "您的眼睛近视度数？",
      note: "当前是文件预览模式，提交不会写入后台。",
    },
  ];

  function track(name, props) {
    if (isFilePreview) return;
    eventQueue.push({ name: name, props: props || {} });
    if (eventQueue.length >= 10) { flushEvents(false); return; }
    if (!flushTimer) flushTimer = setTimeout(function () { flushEvents(false); }, 5000);
  }

  function flushEvents(useBeacon) {
    if (isFilePreview) return;
    if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
    if (!eventQueue.length) return;
    const body = JSON.stringify({
      session_id: sessionId, fingerprint: fingerprint, channel: channel, token: token, events: eventQueue,
    });
    eventQueue = [];
    const url = `/s/${slug}/track`;
    try {
      if (useBeacon && navigator.sendBeacon) {
        navigator.sendBeacon(url, new Blob([body], { type: "application/json" }));
      } else {
        fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: body, keepalive: true }).catch(function () {});
      }
    } catch (e) { /* 埋点失败不影响页面 */ }
  }

  // 页面离开：每次"真实离开"只记一条（切后台或关页），回到页面后再次离开才记下一条；
  // question_id = 离开时停在哪道题（流失点），dwell = 本次会话累计停留
  let leaveSent = false;
  function trackLeave() {
    if (leaveSent) return;
    leaveSent = true;
    track("page_leave", {
      question_id: typeof stepCurrentId !== "undefined" ? stepCurrentId : null,
      dwell_ms: Date.now() - startedAt,
    });
    flushEvents(true);
  }
  window.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") trackLeave();
    else leaveSent = false;  // 回到页面，下次离开重新记
  });
  window.addEventListener("pagehide", trackLeave);

  function splitTiers(list) {
    degreeQuestions = list.filter((q) => q.degree);          // 度数题单独抽出，提交后弹窗收集
    const steps = list.filter((q) => !q.degree);             // 逐题流程不含度数题
    tier1 = steps.filter((q) => (q.tier || 1) === 1);
    tier2 = steps.filter((q) => (q.tier || 1) === 2);
  }

  // 度数弹窗：返回 Promise，resolve 出 {qid: 用户填写}（无度数题则 resolve {}）。
  function askDegree() {
    return new Promise(function (resolve) {
      if (!degreeQuestions.length) { resolve({}); return; }
      const q = degreeQuestions[0];
      const modal = document.getElementById("degreeModal");
      const input = document.getElementById("degreeInput");
      const done = document.getElementById("degreeDone");
      const titleEl = document.getElementById("degreeTitle");
      const subEl = document.getElementById("degreeSub");
      if (!modal || !input || !done) { const e = {}; e[q.id] = ""; resolve(e); return; }
      if (titleEl && q.title) titleEl.textContent = q.title;
      if (subEl) subEl.textContent = q.note || "兑换奖品前需填写镜片度数；若左右眼度数不同，建议填写较低度数；如未填写，默认发放0度镜片。";
      input.innerHTML = '<option value="">请选择度数</option>';
      (q.options || []).forEach(function (value) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value + " 度";
        input.appendChild(option);
      });
      input.value = "";
      input.classList.remove("input-error");
      if (subEl) subEl.classList.remove("degree-sub-error");
      modal.classList.add("is-open");
      modal.setAttribute("aria-hidden", "false");
      track("degree_view", { question_id: q.id });  // 弹了没填就关页：会话里有"弹出度数框"没有"填写度数"
      flushEvents(false);
      const degreeOpenedAt = Date.now();   // 填写度数耗时据此计算
      window.setTimeout(function () { try { input.focus(); } catch (e) {} }, 60);
      done.onclick = function () {
        const raw = (input.value || "").trim();
        if (!raw || (q.options || []).indexOf(raw) === -1) {
          if (subEl) { subEl.textContent = "请选择用于兑奖的镜片度数"; subEl.classList.add("degree-sub-error"); }
          input.classList.add("input-error");
          return;
        }
        done.onclick = null;
        modal.classList.remove("is-open");
        modal.setAttribute("aria-hidden", "true");
        // 停留=度数弹窗弹出到点完成的耗时
        track("degree_done", { question_id: q.id, value: raw || "未填", dwell_ms: Date.now() - degreeOpenedAt });
        const extra = {};
        extra[q.id] = raw;
        resolve(extra);
      };
    });
  }

  const FP_STORAGE_KEY = "survey_device_fp";

  async function computeFingerprint() {
    // 本地生成稳定设备摘要，避免等待境外 FingerprintJS CDN 导致手机首屏卡住。
    const raw = [
      navigator.userAgent || "", navigator.platform || "", navigator.language || "",
      screen.width + "x" + screen.height, screen.colorDepth || "",
      Intl.DateTimeFormat().resolvedOptions().timeZone || "",
      navigator.hardwareConcurrency || "", navigator.deviceMemory || "",
      navigator.maxTouchPoints || "",
    ].join("|");
    try {
      const bytes = new TextEncoder().encode(raw);
      const digest = await crypto.subtle.digest("SHA-256", bytes);
      return "fp-" + Array.from(new Uint8Array(digest)).map(function (b) {
        return b.toString(16).padStart(2, "0");
      }).join("").slice(0, 32);
    } catch (e) {
      let hash = 5381;
      for (let i = 0; i < raw.length; i += 1) hash = ((hash << 5) + hash) ^ raw.charCodeAt(i);
      return "fp-local-" + (hash >>> 0).toString(16);
    }
  }

  // 设备身份持久化：同一设备刷新/换网都复用同一指纹，
  // 即便 FingerprintJS（国外 CDN）加载失败、回退到随机值也不会每次变。
  async function getFingerprint() {
    try {
      const cached = localStorage.getItem(FP_STORAGE_KEY);
      if (cached) return cached;
    } catch (e) {
      /* localStorage 不可用（隐私模式等），降级为每次计算 */
    }
    const value = await computeFingerprint();
    try {
      localStorage.setItem(FP_STORAGE_KEY, value);
    } catch (e) {
      /* 忽略写入失败 */
    }
    return value;
  }

  // 采集客户端设备信息（非侵入性，浏览器公开 API）。
  function collectDevice() {
    if (isFilePreview) return {};
    const nav = navigator || {};
    const s = window.screen || {};
    let timezone = "";
    try { timezone = Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (e) {}
    return {
      ua: nav.userAgent || "",
      platform: nav.platform || "",
      vendor: nav.vendor || "",
      language: nav.language || "",
      languages: (nav.languages || []).join(","),
      screen: (s.width || 0) + "x" + (s.height || 0),
      pixel_ratio: window.devicePixelRatio || 1,
      color_depth: s.colorDepth || null,
      viewport: window.innerWidth + "x" + window.innerHeight,
      timezone: timezone,
      touch_points: nav.maxTouchPoints || 0,
      hardware_concurrency: nav.hardwareConcurrency || null,
      device_memory: nav.deviceMemory || null,
      online: nav.onLine,
    };
  }

  function setPageMode(mode) {
    const cls = mode === "result" ? "page-result" : (mode === "plain" ? "page-plain" : "page-question");
    document.body.classList.remove("page-question", "page-result", "page-plain", "page-ineligible");
    document.body.classList.add(cls);
    if (mode !== "question") {
      const wrap = document.querySelector(".wrap");
      if (wrap) {
        wrap.classList.remove("is-extended-artwork");
        wrap.style.minHeight = "";
        wrap.style.removeProperty("--art-extension-top-px");
      }
    }
  }

  function showOnlyTitle(text, variant) {
    setPageMode("plain");
    if (variant === "ineligible") document.body.classList.add("page-ineligible");
    document.getElementById("title").textContent = text;
    document.getElementById("form").style.display = "none";
    document.getElementById("submitWrap").style.display = "none";
    const sideHints = document.getElementById("swipeSideHints");
    if (sideHints) sideHints.style.display = "none";
  }

  function fitSingleLineToSlot(el, minPx) {
    if (!el) return;
    el.style.fontSize = "";
    const styles = window.getComputedStyle(el);
    let size = parseFloat(styles.fontSize) || 15;
    const floor = minPx || 11;
    const slotWidth = el.parentElement ? el.parentElement.clientWidth : el.clientWidth;
    const slotHeight = el.parentElement ? el.parentElement.clientHeight : el.clientHeight;
    el.style.fontSize = size + "px";
    while (size > floor && (el.scrollHeight > slotHeight || el.scrollWidth > slotWidth)) {
      size -= 0.5;
      el.style.fontSize = size + "px";
    }
  }

  function fitTitleToSlot(el) {
    if (!el) return;
    const wrap = document.querySelector(".wrap");
    const scale = artworkCanvasScale(wrap);
    el.style.fontSize = "";
    const styles = window.getComputedStyle(el);
    let size = parseFloat(styles.fontSize) || 22;
    const floor = Math.max(12, Math.round(15 * scale));
    const textLength = (el.textContent || "").replace(/\s/g, "").length;
    const density = Math.max(0.78, 1 - Math.max(textLength - 24, 0) * 0.009);
    size = Math.max(floor, size * density);
    el.style.fontSize = size + "px";
    while (size > floor && (el.scrollHeight > el.clientHeight || el.scrollWidth > el.clientWidth)) {
      size -= 0.5;
      el.style.fontSize = size + "px";
    }
  }

  function artworkNaturalHeight(wrap) {
    return wrap ? wrap.clientWidth * 1672 / 941 : 0;
  }

  function artworkCanvasScale(wrap) {
    return wrap ? Math.min(1, wrap.clientWidth / 640) : 1;
  }

  function syncArtworkSlotVars(wrap) {
    if (!wrap) return;
    const naturalHeight = artworkNaturalHeight(wrap);
    const slots = {
      "--progress-top-px": 0.118,
      "--side-arrow-top-px": 0.54,
      "--question-top-px": 0.198,
      "--question-height-px": 0.162,
      "--options-top-px": 0.414,
      "--art-bottom-slice-height-px": 0.17,
    };
    Object.keys(slots).forEach(function (name) {
      wrap.style.setProperty(name, (naturalHeight * slots[name]) + "px");
    });
  }

  function tallestChoiceTextHeight(box) {
    return Array.prototype.reduce.call(box.querySelectorAll("label"), function (height, label) {
      return Math.max(height, label.scrollHeight);
    }, 0);
  }

  // 行高装不下折行文本时：逐步缩小字号（到 10.5px 下限），装下返回 true。
  function shrinkChoiceFontUntilFit(box, rowHeight) {
    const firstLabel = box.querySelector("label");
    let size = firstLabel ? (parseFloat(window.getComputedStyle(firstLabel).fontSize) || 16) : 16;
    while (tallestChoiceTextHeight(box) > rowHeight + 1) {
      if (size <= 10.5) return false;
      size -= 0.5;
      box.style.setProperty("--choice-font-size", size.toFixed(1) + "px");
      box.style.setProperty("--choice-line-height", "1.18");
    }
    return true;
  }

  function compactChoiceGap(rowCount, wrap) {
    if (rowCount <= 8) return "";
    const width = wrap ? wrap.clientWidth : 390;
    const px = Math.max(2, Math.min(4, width * 0.006));
    return px.toFixed(1) + "px";
  }

  function fitChoiceRowsInsideArtwork(box, designHeight, wrap) {
    const rows = visibleArtworkChoiceRows(box);
    // 行高/字号只按选项行(label)计算：「其他」输入框/备注不占槽位，
    // 勾选「其他」显形输入框时全局行高字号保持不变（防整块突然缩小）
    const labelRows = rows.filter(function (el) { return el.tagName === "LABEL"; });
    const extraRows = rows.filter(function (el) { return el.tagName !== "LABEL"; });
    const rowCount = Math.max(labelRows.length, 1);
    const gapValue = compactChoiceGap(rowCount, wrap);
    if (gapValue) box.style.setProperty("--option-gap", gapValue);
    else box.style.removeProperty("--option-gap");
    const styles = window.getComputedStyle(box);
    const gap = parseFloat(styles.rowGap) || 0;
    const padBottom = parseFloat(styles.paddingBottom) || 0;  // 「其他」输入框可见时的底部内边距
    // 非 label 行（其他输入框/备注）按自身渲染高度累加，不参与槽位平摊
    const extraHeight = extraRows.reduce(function (total, el) {
      return total + el.offsetHeight + gap;
    }, 0);
    // 行高按统一基准槽位（至少 8 行）计算，少选项的题目与多选项题目保持一致的行高与间距。
    const slotCount = parseInt(box.style.getPropertyValue("--option-slot-count"), 10) || Math.max(rowCount, 8);
    const layoutSlotCount = Math.max(slotCount, rowCount);
    // 以设计槽位高为基准（而非 clientHeight）：渲染高度被量测兜底加高后,下一轮重排仍从同一基准出发,布局收敛稳定
    let availableHeight = Math.max(0, designHeight || box.clientHeight);
    if (rowCount > 8 && wrap) {
      // 多选项紧凑模式：预算高度 = 提交按钮标准槽位(88.5%)之上、扣除按钮前间距，
      // 让选项 + 提交按钮收进底图原始框内，不再叠到底部装饰区/向下延伸
      const naturalHeight = artworkNaturalHeight(wrap);
      const submitGap = Math.max(28, wrap.clientWidth * 0.04);
      const budget = naturalHeight * 0.885 - naturalHeight * 0.414 - submitGap;
      if (budget > 0) availableHeight = Math.min(availableHeight, budget);
    }
    const rowHeight = (availableHeight - Math.max(layoutSlotCount - 1, 0) * gap) / layoutSlotCount;
    if (rowHeight <= 0) return { renderHeight: designHeight, contentHeight: designHeight };
    const finalRowHeight = Math.max(22, rowHeight);
    // 紧凑模式按实际占用高度收口（背景光晕/提交按钮紧跟最后一个选项）；常规题维持设计槽位高
    const compactUsedHeight = finalRowHeight * rowCount + gap * Math.max(rowCount - 1, 0) + extraHeight + padBottom;
    const contentHeight = rowCount > 8 ? compactUsedHeight : availableHeight;
    const renderHeight = rowCount > 8 ? compactUsedHeight : designHeight;
    box.style.setProperty("--option-row-height", finalRowHeight + "px");
    box.style.setProperty("--options-content-height", contentHeight + "px");
    box.style.setProperty("--options-render-height", renderHeight + "px");
    // 适配签名：行数×槽位高×画布宽不变 → 字号/缩字/flow 判定沿用首次适配结果。
    // 勾选选项触发的重排只更新高度定位，字体/折行绝不跳变。
    const fitSig = rowCount + "|" + Math.round(availableHeight) + "|" + Math.round(wrap ? wrap.clientWidth : 0);
    const sigChanged = box.dataset.fitSig !== fitSig;
    if (sigChanged) {
      box.dataset.fitSig = fitSig;
      if (rowCount > 8) {
        const fontSize = Math.max(10.8, Math.min(15, finalRowHeight * 0.43));
        box.style.setProperty("--choice-font-size", fontSize.toFixed(1) + "px");
        box.style.setProperty("--choice-line-height", finalRowHeight < 30 ? "1.12" : "1.16");
      } else {
        box.style.removeProperty("--choice-font-size");
        box.style.removeProperty("--choice-line-height");
      }
    }
    // 量测兜底：折行文本超过行高（窄画布/长选项）→ 先缩字号，仍装不下则加高行并延伸渲染高度，
    // 提交按钮下移与画布底部延伸由既有 positionSubmitAfter / reserveArtworkBottomSpace 承接。
    if (sigChanged) {
      // 量测兜底判定只在签名变化时做一次：折行装不下 → flow 模式
      // （height auto + min-height 槽位行高，只有装不下的行自然加高）
      if (tallestChoiceTextHeight(box) > finalRowHeight + 1 && !shrinkChoiceFontUntilFit(box, finalRowHeight)) {
        box.classList.add("art-choices-flow");
      } else {
        box.classList.remove("art-choices-flow");
      }
    }
    if (box.classList.contains("art-choices-flow")) {
      const grownRenderHeight = labelRows.reduce(function (total, el) {
        return total + Math.max(finalRowHeight, Math.ceil(el.scrollHeight));
      }, 0) + gap * Math.max(rowCount - 1, 0) + extraHeight + padBottom;
      box.style.setProperty("--options-render-height", grownRenderHeight + "px");
      box.scrollTop = 0;
      return { renderHeight: grownRenderHeight, contentHeight: grownRenderHeight };
    }
    box.scrollTop = 0;
    return { renderHeight: renderHeight, contentHeight: contentHeight };
  }

  function measuredOptionsHeight(box, fallbackHeight) {
    if (box.classList.contains("art-choices")) {
      return fallbackHeight || box.getBoundingClientRect().height || box.clientHeight || 0;
    }
    const boxTop = box.getBoundingClientRect().top;
    const children = Array.prototype.slice.call(box.children);
    return children.reduce(function (height, child) {
      return Math.max(height, child.getBoundingClientRect().bottom - boxTop);
    }, fallbackHeight || box.scrollHeight || 0);
  }

  function visibleArtworkChoiceRows(box) {
    return Array.prototype.filter.call(box.children, function (child) {
      const style = window.getComputedStyle(child);
      return style.display !== "none";
    });
  }

  function revealArtworkOtherInput(input) {
    if (!input) return;
    const box = input.closest(".art-choices");
    if (!box) {
      input.scrollIntoView({ block: "nearest", inline: "nearest" });
      return;
    }
    box.scrollTop = 0;
  }

  function scheduleSubmitPosition(box, fallbackHeight, wrap) {
    window.requestAnimationFrame(function () {
      positionSubmitAfter(box, measuredOptionsHeight(box, fallbackHeight), wrap);
    });
  }

  function fitArtworkText(scope) {
    window.requestAnimationFrame(function () {
      const root = scope || document;
      Array.prototype.forEach.call(root.querySelectorAll(".art-options"), function (box) {
        const count = parseInt(box.style.getPropertyValue("--option-count"), 10) || Math.max(box.children.length, 1);
        const slotCount = parseInt(box.style.getPropertyValue("--option-slot-count"), 10) || Math.max(count, 8);
        const wrap = document.querySelector(".wrap");
        syncArtworkSlotVars(wrap);
        const styles = window.getComputedStyle(box);
        const gap = parseFloat(styles.rowGap) || 0;
        if (box.classList.contains("art-choices")) {
          const designHeight = wrap ? artworkNaturalHeight(wrap) * 0.488 : box.clientHeight;
          const fitted = fitChoiceRowsInsideArtwork(box, designHeight, wrap);
          scheduleSubmitPosition(box, fitted.renderHeight, wrap);
          return;
        }
        const renderHeight = measuredOptionsHeight(box, box.scrollHeight);
        box.style.setProperty("--options-render-height", renderHeight + "px");
        scheduleSubmitPosition(box, renderHeight, wrap);
      });
      fitTitleToSlot(root.querySelector(".q-title"));
      fitSingleLineToSlot(root.querySelector(".code"), 16);
    });
  }

  function settleArtworkLayout(scope) {
    fitArtworkText(scope);
    [80, 180, 360].forEach(function (delay) {
      window.setTimeout(function () { fitArtworkText(scope); }, delay);
    });
  }

  function reserveArtworkBottomSpace(wrap, submitWrap, submitTop, extensionTop) {
    syncArtworkSlotVars(wrap);
    const naturalHeight = artworkNaturalHeight(wrap);
    const safeGap = Math.max(18, wrap.clientWidth * 0.04);
    const neededHeight = submitTop + submitWrap.offsetHeight + safeGap;
    const finalHeight = Math.max(naturalHeight, neededHeight);
    wrap.style.minHeight = finalHeight + "px";
    const isExtended = finalHeight > naturalHeight + 2;
    wrap.classList.toggle("is-extended-artwork", isExtended);
    if (isExtended) {
      const coverTop = Math.max(naturalHeight * 0.39, extensionTop || 0);
      wrap.style.setProperty("--art-extension-top-px", coverTop + "px");
    } else {
      wrap.style.removeProperty("--art-extension-top-px");
    }
  }

  function measuredOptionsBottomFromWrap(box, wrap) {
    const wrapTop = wrap.getBoundingClientRect().top;
    if (box.classList.contains("art-choices")) {
      return box.getBoundingClientRect().bottom - wrapTop;
    }
    return Array.prototype.reduce.call(box.children, function (bottom, child) {
      return Math.max(bottom, child.getBoundingClientRect().bottom - wrapTop);
    }, 0);
  }

  function positionSubmitAfter(box, contentHeight, wrap) {
    const submitWrap = document.getElementById("submitWrap");
    if (!submitWrap || !wrap || !document.body.classList.contains("page-question")) return;
    const gap = Math.max(28, wrap.clientWidth * 0.04);
    const top = Math.max(
      box.offsetTop + contentHeight + gap,
      measuredOptionsBottomFromWrap(box, wrap) + gap
    );
    submitWrap.style.top = top + "px";
    reserveArtworkBottomSpace(wrap, submitWrap, top, Math.max(0, box.offsetTop - gap));
  }

  // 构建单个题目的 DOM 块（可预填已选答案）。
  function buildBlock(q, prefill) {
    const block = document.createElement("div");
    block.className = "q-block";
    block.dataset.qid = q.id;
    const title = document.createElement("div");
    title.className = "q-title";
    const titleText = document.createElement("span");
    titleText.className = "q-title-text";
    titleText.textContent = q.title;
    let hint = { single: "（单选）", text: "（填空）" }[q.type];
    if (q.type === "multi") hint = q.max ? `（可多选，最多${q.max}项）` : "（可多选）";
    if (q.degree) hint = "（选填）";
    else if (q.optional) hint = (hint || "") + "（选填）";
    if (hint) {
      const tag = document.createElement("span");
      tag.className = "q-hint";
      tag.textContent = " " + hint;
      titleText.appendChild(tag);
    }
    title.appendChild(titleText);
    block.appendChild(title);
    const controls = document.createElement("div");
    const isChoiceQuestion = (q.type === "single" || q.type === "multi") && q.style !== "scale";
    controls.className = isChoiceQuestion ? "art-options art-choices" : "art-options art-inputs";
    const optionCount = Math.max((q.options || []).length, 1);
    if (isChoiceQuestion && optionCount > 8) controls.classList.add("is-long-list");
    controls.style.setProperty("--option-count", String(optionCount));
    controls.style.setProperty("--option-slot-count", String(Math.max(optionCount, 8)));
    block.appendChild(controls);
    if (q.note) {
      const note = document.createElement("div");
      note.className = "q-note";
      note.textContent = q.note;
      controls.appendChild(note);
    }
    if (q.type === "single" && q.style === "scale") {
      // 打分题：横向方块选择（单选）。
      const row = document.createElement("div");
      row.className = "scale-row";
      (q.options || []).forEach((opt) => {
        const box = document.createElement("label");
        box.className = "scale-box";
        const input = document.createElement("input");
        input.type = "radio";
        input.name = q.id;
        input.value = opt;
        if (prefill === opt) { input.checked = true; box.classList.add("on"); }
        input.addEventListener("change", function () {
          row.querySelectorAll(".scale-box").forEach((b) => b.classList.remove("on"));
          if (input.checked) box.classList.add("on");
          maybeAutoAdvanceSingleChoice(q);
        });
        box.appendChild(input);
        box.appendChild(document.createTextNode(opt));
        row.appendChild(box);
      });
      controls.appendChild(row);
    } else if (q.type === "single" || q.type === "multi") {
      const sel = q.type === "multi" ? (Array.isArray(prefill) ? prefill : []) : prefill;
      const otherPairs = [];
      (q.options || []).forEach((opt) => {
        const isOther = opt.indexOf("其他") === 0;
        let checked = false, otherText = "";
        const arr = q.type === "multi" ? sel : (sel == null ? [] : [sel]);
        arr.forEach((s) => {
          if (s === opt) checked = true;
          else if (isOther && typeof s === "string" && s.indexOf(opt + "：") === 0) {
            checked = true;
            otherText = s.slice((opt + "：").length);
          }
        });
        const label = document.createElement("label");
        const input = document.createElement("input");
        input.type = q.type === "single" ? "radio" : "checkbox";
        input.name = q.id;
        input.value = opt;
        if (checked) input.checked = true;
        input.addEventListener("change", function () { maybeAutoAdvanceSingleChoice(q); });
        const labelText = document.createElement("span");
        labelText.className = "choice-text";
        labelText.textContent = opt;
        label.appendChild(input);
        label.appendChild(labelText);
        controls.appendChild(label);
        if (isOther) {
          const ti = document.createElement("input");
          ti.type = "text";
          ti.size = 1;  // 固有宽度钉最小，显示长度交给 CSS 的 min/max-width 控制
          ti.className = "other-input";
          ti.dataset.for = opt;
          ti.placeholder = "请填写（必填）…";
          ti.maxLength = q.other_max || 300;
          ti.value = otherText;
          ti.style.display = checked ? "block" : "none";
          ti.addEventListener("input", function () {
            ti.classList.remove("input-error");
            block.classList.remove("q-error");
          });
          controls.appendChild(ti);
          otherPairs.push({ ctrl: input, ti: ti });
        }
      });
      if (otherPairs.length) {
        if (otherPairs.some((p) => p.ctrl.checked)) controls.classList.add("has-visible-other");
        block.addEventListener("change", function () {
          let visibleOtherInput = null;
          let hasVisibleOther = false;
          otherPairs.forEach((p) => {
            p.ti.style.display = p.ctrl.checked ? "block" : "none";
            if (p.ctrl.checked) {
              visibleOtherInput = p.ti;
              hasVisibleOther = true;
            }
          });
          controls.classList.toggle("has-visible-other", hasVisibleOther);
          settleArtworkLayout(block);
          if (visibleOtherInput) {
            window.requestAnimationFrame(function () {
              visibleOtherInput.scrollIntoView({ block: "nearest", inline: "nearest" });
              revealArtworkOtherInput(visibleOtherInput);
            });
            window.setTimeout(function () { revealArtworkOtherInput(visibleOtherInput); }, 120);
          }
        });
      }
      // 多选限额：选满后禁用其余未选项。
      if (q.type === "multi" && q.max) {
        const enforceMax = function () {
          const boxes = Array.from(block.querySelectorAll(`input[name="${q.id}"]`));
          const n = boxes.filter((b) => b.checked).length;
          boxes.forEach((b) => { if (!b.checked) b.disabled = n >= q.max; });
        };
        block.addEventListener("change", enforceMax);
        enforceMax();
      }
    } else if (q.degree) {
      const inp = document.createElement("input");
      inp.type = "text";
      inp.name = q.id;
      inp.inputMode = "numeric";
      inp.placeholder = "如 475（不填记为 0 度）";
      if (typeof prefill === "string") inp.value = prefill;
      controls.appendChild(inp);
    } else {
      const ta = document.createElement("textarea");
      ta.name = q.id;
      ta.rows = 3;
      if (typeof prefill === "string") ta.value = prefill;
      controls.appendChild(ta);
    }
    return block;
  }

  // 把「其他」选项的选中值并入用户填写：其他 → 其他：用户填写。
  function withOtherText(block, optVal) {
    if (!block || optVal.indexOf("其他") !== 0) return optVal;
    const ti = block.querySelector(`.other-input[data-for="${optVal}"]`);
    const t = ti && ti.value.trim();
    return t ? (optVal + "：" + t) : optVal;
  }

  // 勾选了「其他」却没填写 → 返回这些空填写框（必填校验用）。
  function emptyOtherInputs(q) {
    const form = document.getElementById("form");
    const block = form.querySelector(`.q-block[data-qid="${q.id}"]`);
    if (!block) return [];
    return Array.from(form.querySelectorAll(`input[name="${q.id}"]:checked`))
      .filter((el) => el.value.indexOf("其他") === 0)
      .map((el) => block.querySelector(`.other-input[data-for="${el.value}"]`))
      .filter((ti) => ti && !ti.value.trim());
  }

  // 从当前表单读取单题答案。
  function readAnswer(q) {
    const form = document.getElementById("form");
    const block = form.querySelector(`.q-block[data-qid="${q.id}"]`);
    if (q.type === "multi") {
      return Array.from(form.querySelectorAll(`input[name="${q.id}"]:checked`)).map((el) => withOtherText(block, el.value));
    }
    if (q.type === "single") {
      const el = form.querySelector(`input[name="${q.id}"]:checked`);
      return el ? withOtherText(block, el.value) : "";
    }
    const el = form.querySelector(`[name="${q.id}"]`);
    return el ? el.value : "";
  }

  function isAnswered(q, val) {
    if (q.type === "multi") return Array.isArray(val) && val.length > 0;
    return typeof val === "string" ? val.trim() !== "" : !!val;
  }

  // 计算列表里当前可见的题：递归判定 show_if（限同层），无 show_if 恒可见。
  function evalVisible(list, answersAll) {
    const byId = {};
    list.forEach((q) => { byId[q.id] = q; });
    function visible(q) {
      if (!q.show_if) return true;
      const dep = byId[q.show_if.q];
      if (dep && !visible(dep)) return false; // 依赖题不可见 → 本题不可见
      const val = answersAll[q.show_if.q];
      const selected = Array.isArray(val) ? val : [val]; // 兼容单选(字符串)与多选(数组)触发题
      const wanted = q.show_if.in || [];
      return selected.some((v) => wanted.indexOf(v) !== -1);
    }
    return list.filter(visible);
  }

  function showResult(html, color) {
    setPageMode("result");
    const result = document.getElementById("result");
    result.style.display = "block";
    result.style.color = color || "";
    result.innerHTML = html;
  }

  function hideForm() {
    document.getElementById("form").style.display = "none";
    document.getElementById("submitWrap").style.display = "none";
    document.getElementById("progress").style.display = "none";
    const sideHints = document.getElementById("swipeSideHints");
    if (sideHints) sideHints.style.display = "none";
  }

  // 兼容非 HTTPS（局域网 http）环境：clipboard API 不可用时回退到 execCommand。
  function fallbackCopy(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try { document.execCommand("copy"); } catch (e) { /* 忽略 */ }
    document.body.removeChild(ta);
  }

  function copyText(text, btn) {
    function done() {
      if (!btn) return;
      btn.textContent = "已复制 ✓";
      setTimeout(function () { btn.textContent = "复制兑换码"; }, 1500);
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done).catch(function () { fallbackCopy(text); done(); });
    } else {
      fallbackCopy(text);
      done();
    }
  }

  // 结果页展示兑换码（复制动作由「去兑奖」按钮承担）。
  function showCodeResult(introHtml, code) {
    showResult(
      '<div class="reward-heading"><div class="reward-heading-line">' +
        '<img src="/static/moody-logo-original.webp?v=1" alt="moody">' +
        '<span><em>用户调研</em>问卷</span></div></div>' +
      '<div class="reward-copy">' + introHtml + '</div>' +
      '<div class="code-box"><div class="code">' + code + "</div></div>" +
      '<section class="reward-instructions"><img class="reward-notes-star" src="/static/reward-notes-star.png?v=1" alt="">' +
        '<h2>使用说明</h2><ol>' +
          '<li>点击「去兑奖」会自动复制专属兑换码并打开天猫链接。</li>' +
          '<li>下单时请在订单备注中粘贴兑换码，兑换码已包含奖品规格和度数。</li>' +
          '<li>每个兑换码仅限使用一次，工作人员核销后无法重复兑奖。</li>' +
        '</ol></section>'
    );
    fitArtworkText(document);
  }

  // 「去兑奖」按钮：自动复制兑换码并跳转到商品详情页（新标签）。
  // code 为空（已提交过等场景，手里没有当前码）时只跳转、不复制。
  function showRedeemAction(code) {
    if (!newProductUrl) return;
    const shownAt = Date.now();   // 兑奖码页展示时刻，点击耗时据此计算
    const btn = document.getElementById("newProductBtn");
    btn.textContent = "去兑奖 →";
    btn.onclick = function () {
      // 内容=带去兑奖的兑换码；停留=看到码页到点击的耗时
      track("redeem_click", { value: code || "无码", dwell_ms: Date.now() - shownAt });
      flushEvents(false);
      if (isMiniapp && window.my && typeof window.my.postMessage === "function") {
        // 小程序内：webview 直接跳 tmall 会被业务域名白名单拦，交给壳原生打开商品 + 复制码
        window.my.postMessage({ type: "open_product", url: newProductUrl, code: code || "" });
        return;
      }
      if (code) copyText(code); // 用户手势内同步触发复制，再打开商品页
      // App 内置 WebView 常拦截 window.open(_blank)：打不开就在当前 WebView 跳转。
      let win = null;
      try { win = window.open(newProductUrl, "_blank"); } catch (e) { win = null; }
      if (!win) location.href = newProductUrl;
    };
    document.getElementById("newProductWrap").style.display = "block";
  }

  // ===== 逐题作答（单题模式）=====
  let stepList = [];     // 当前层题目
  let stepKind = "";     // 'tier1' | 'tier2'
  let stepAnswers = {};  // 已答累计 {qid: value}
  let stepCurrentId = null;
  const STEP_TRANSITION_MS = 280;

  function stepById() {
    const m = {};
    stepList.forEach((q) => { m[q.id] = q; });
    return m;
  }

  function stepVisibleList() {
    return evalVisible(stepList, stepAnswers);
  }

  function prevVisibleId() {
    const vis = stepVisibleList();
    const xi = vis.findIndex((v) => v.id === stepCurrentId);
    return xi > 0 ? vis[xi - 1].id : null;
  }

  function currentStepPosition() {
    const vis = stepVisibleList();
    return { list: vis, index: vis.findIndex((v) => v.id === stepCurrentId) };
  }

  function shouldAutoAdvanceSingleChoice(q) {
    if (!q || q.type !== "single") return false;
    if ((q.options || []).some((o) => o.indexOf("其他") === 0)) return false;
    const pos = currentStepPosition();
    return pos.index >= 0 && pos.index < pos.list.length - 1;
  }

  function maybeAutoAdvanceSingleChoice(q) {
    // 先把单选答案写入状态，再重算分支；例如第 3 题选择「只戴美瞳」后会立即出现第 4-6 题。
    stepAnswers[q.id] = readAnswer(q);
    if (!shouldAutoAdvanceSingleChoice(q)) return;
    window.setTimeout(function () {
      if (stepCurrentId === q.id && shouldAutoAdvanceSingleChoice(q)) advanceStep();
    }, 180);
  }

  let swipeNavigationAttached = false;
  let sideArrowNavigationAttached = false;
  let swipeStart = null;

  function canStartSwipeNavigation(target) {
    if (!target || !target.closest) return true;
    return !target.closest("#submitWrap, #newProductWrap, textarea, input[type=text], button");
  }

  function startSwipeNavigation(x, y, target) {
    if (!document.body.classList.contains("page-question")) return;
    if (!canStartSwipeNavigation(target)) return;
    swipeStart = { x: x, y: y };
  }

  function finishSwipeNavigation(x, y) {
    if (!swipeStart || !document.body.classList.contains("page-question")) {
      swipeStart = null;
      return;
    }
    const dx = x - swipeStart.x;
    const dy = y - swipeStart.y;
    swipeStart = null;
    if (Math.abs(dx) < 54 || Math.abs(dx) < Math.abs(dy) * 1.2) return;
    handleSwipeNavigation(dx < 0 ? "next" : "prev");
  }

  function handleSwipeNavigation(direction) {
    if (!stepCurrentId) return;
    if (direction === "prev") { goBackStep(); return; }
    const pos = currentStepPosition();
    if (pos.index >= 0 && pos.index < pos.list.length - 1) advanceStep();
  }

  function attachSwipeNavigation() {
    const wrap = document.querySelector(".wrap");
    if (!wrap || swipeNavigationAttached) return;
    swipeNavigationAttached = true;
    wrap.addEventListener("touchstart", function (ev) {
      const touch = ev.changedTouches && ev.changedTouches[0];
      if (touch) startSwipeNavigation(touch.clientX, touch.clientY, ev.target);
    }, { passive: true });
    wrap.addEventListener("touchend", function (ev) {
      const touch = ev.changedTouches && ev.changedTouches[0];
      if (touch) finishSwipeNavigation(touch.clientX, touch.clientY);
    }, { passive: true });
    wrap.addEventListener("pointerdown", function (ev) {
      if (ev.pointerType === "touch") return;
      startSwipeNavigation(ev.clientX, ev.clientY, ev.target);
    });
    wrap.addEventListener("pointerup", function (ev) {
      if (ev.pointerType === "touch") return;
      finishSwipeNavigation(ev.clientX, ev.clientY);
    });
  }

  function attachSideArrowNavigation() {
    if (sideArrowNavigationAttached) return;
    const left = document.getElementById("swipeSideLeft");
    const right = document.getElementById("swipeSideRight");
    if (!left || !right) return;
    sideArrowNavigationAttached = true;
    left.addEventListener("click", function () { handleSwipeNavigation("prev"); });
    right.addEventListener("click", function () { handleSwipeNavigation("next"); });
  }

  // 活动规则：右上角悬浮按钮点击展开面板，点关闭按钮或遮罩收起。
  function attachRulesPanel() {
    const fab = document.getElementById("rulesFab");
    const modal = document.getElementById("rulesModal");
    const close = document.getElementById("rulesClose");
    if (!fab || !modal) return;
    function open() { modal.classList.add("is-open"); modal.setAttribute("aria-hidden", "false"); }
    function hide() { modal.classList.remove("is-open"); modal.setAttribute("aria-hidden", "true"); }
    fab.addEventListener("click", open);
    if (close) close.addEventListener("click", hide);
    modal.addEventListener("click", function (ev) { if (ev.target === modal) hide(); });
  }

  function updateSwipeHint(total) {
    // 滑动提示文本已移除，只保留两侧箭头
    const sideHints = document.getElementById("swipeSideHints");
    const visible = total > 1 && document.body.classList.contains("page-question");
    if (sideHints) sideHints.style.display = visible ? "block" : "none";
  }

  function supportsStepMotion() {
    return !window.matchMedia || !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function transitionStepBlock(form, nextBlock, direction) {
    const currentBlock = form.querySelector(".q-block");
    const animate = !!direction && !!currentBlock && supportsStepMotion();
    if (!animate) {
      form.innerHTML = "";
      form.appendChild(nextBlock);
      return;
    }
    const enterClass = direction === "prev" ? "is-slide-enter-prev" : "is-slide-enter-next";
    const leaveClass = direction === "prev" ? "is-slide-leave-prev" : "is-slide-leave-next";
    nextBlock.classList.add("is-slide-ready", enterClass);
    form.appendChild(nextBlock);
    window.requestAnimationFrame(function () {
      currentBlock.classList.add(leaveClass);
      nextBlock.classList.remove("is-slide-ready", enterClass);
    });
    window.setTimeout(function () {
      if (nextBlock.parentNode !== form) return;
      Array.prototype.forEach.call(form.querySelectorAll(".q-block"), function (block) {
        if (block !== nextBlock) block.remove();
      });
    }, STEP_TRANSITION_MS + 60);
  }

  // 仅保留当前可见题的答案（分支切换后剔除被隐藏题的旧答案）。
  function visibleAnswers() {
    const out = {};
    stepVisibleList().forEach((q) => { out[q.id] = stepAnswers[q.id]; });
    return out;
  }

  // 进入某一层逐题作答。
  function beginTier(list, kind) {
    setPageMode("question");
    stepList = list;
    stepKind = kind;
    stepAnswers = {};
    stepCurrentId = null;
    document.getElementById("result").style.display = "none";
    document.getElementById("newProductWrap").style.display = "none";
    const vis = stepVisibleList();
    if (!vis.length) { finishTier(); return; }
    stepCurrentId = vis[0].id;
    renderStep();
  }

  function renderStep(direction) {
    const q = stepById()[stepCurrentId];
    const form = document.getElementById("form");
    const block = buildBlock(q, stepAnswers[q.id]);
    transitionStepBlock(form, block, direction);
    form.style.display = "block";

    const vis = stepVisibleList();
    const xi = vis.findIndex((v) => v.id === stepCurrentId);
    const isLast = xi === vis.length - 1;
    track("question_view", { question_id: q.id, tier: q.tier || 1, index: xi + 1 });
    questionEnteredAt = Date.now();   // 翻题事件据此上报刚离开那道题的停留时长
    renderProgress(xi + 1, vis.length);
    renderStepNav(isLast);
    settleArtworkLayout(block);

    form.oninput = null;
  }

  function renderProgress(x, n) {
    document.getElementById("progress").style.display = "block";
    const pct = n > 0 ? Math.round((x / n) * 100) : 0;
    document.getElementById("progressFill").style.width = pct + "%";
    document.getElementById("progressText").innerHTML =
      '第 <span class="num">' + x + '</span> 题 / 共 <span class="num">' + n + '</span> 题';
    updateSwipeHint(n);
  }

  // 逐题切换改由滑动承载，只有最后一题显示提交动作。
  function renderStepNav(isLast) {
    const wrap = document.getElementById("submitWrap");
    wrap.innerHTML = "";
    if (isLast) {
      wrap.style.display = "block";
      appendTierActions(wrap, false);
      return;
    }
    wrap.style.display = "none";
  }

  // 在结束位置追加该层的动作按钮（先校验当前题已答再执行）。
  function appendTierActions(wrap, topMargin) {
    if (stepKind === "tier1") {
      const submit = mkButton("下一步", function () { finishCurrentThen(completeTier1ByRoute); });
      if (topMargin) submit.style.marginTop = "10px";
      wrap.appendChild(submit);
    } else {
      const up = mkButton("提交问卷", function () { finishCurrentThen(submitTier2); });
      if (topMargin) up.style.marginTop = "10px";
      wrap.appendChild(up);
    }
  }

  // 校验当前题已答 → 执行结束动作。
  function finishCurrentThen(action) {
    if (stepCurrentId && !saveCurrent()) { flagInvalid(); return; }
    action();
  }

  function saveCurrent() {
    const q = stepById()[stepCurrentId];
    const val = readAnswer(q);
    stepAnswers[q.id] = val;
    // 选填题可空；勾了「其他」必须填写说明，否则不算已答。
    const answered = (q.optional === true)
      || (isAnswered(q, val) && emptyOtherInputs(q).length === 0);
    if (answered) track("answer", { question_id: q.id, value: val });
    return answered;
  }

  // 校验失败时高亮：题块 + 空的「其他」填写框。
  function flagInvalid() {
    const block = document.querySelector(".q-block");
    if (block) block.classList.add("q-error");
    const q = stepById()[stepCurrentId];
    const empties = q ? emptyOtherInputs(q) : [];
    empties.forEach((ti) => ti.classList.add("input-error"));
    if (empties.length) empties[0].focus();
  }

  function advanceStep() {
    if (!saveCurrent()) { flagInvalid(); return; }
    track("nav_next", { question_id: stepCurrentId, dwell_ms: questionDwellMs() });
    const vis = stepVisibleList();
    const xi = vis.findIndex((v) => v.id === stepCurrentId);
    if (xi >= 0 && xi < vis.length - 1) stepCurrentId = vis[xi + 1].id;
    renderStep("next"); // 已是最后一题时，renderStep 会就地显示提交/继续按钮
  }

  function goBackStep() {
    saveCurrent(); // 保留当前答案
    track("nav_prev", { from: stepCurrentId, dwell_ms: questionDwellMs() });
    const pid = prevVisibleId();
    if (!pid) return;
    stepCurrentId = pid;
    renderStep("prev");
  }

  function mkButton(text, onclick, cls) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = text;
    if (cls) b.className = cls;
    b.onclick = onclick;
    return b;
  }

  function setActionsDisabled(d) {
    Array.prototype.forEach.call(
      document.getElementById("submitWrap").querySelectorAll("button"),
      function (b) { b.disabled = d; }
    );
  }

  // 边界情况：某层没有任何可见题时，直接展示结束动作。
  function finishTier() {
    document.getElementById("progress").style.display = "none";
    document.getElementById("form").style.display = "none";
    const sideHints = document.getElementById("swipeSideHints");
    if (sideHints) sideHints.style.display = "none";
    const wrap = document.getElementById("submitWrap");
    wrap.style.display = "block";
    wrap.innerHTML = "";
    appendTierActions(wrap, false);
  }

  // 提交 Tier 1；成功返回数据，失败返回 null（已就地提示）。
  async function postTier1(extraAnswers) {
    setActionsDisabled(true);
    if (isFilePreview) {
      return {
        redeem_code: "WJ-TVENRN-02-0",
        status: "preview",
        tier: 1,
        display_code: "WJ-TVENRN-02-0",
      };
    }
    const body = {
      fingerprint, answers: Object.assign({}, visibleAnswers(), extraAnswers || {}),
      elapsed_ms: Date.now() - startedAt,
      channel, token,
      device: collectDevice(),
      session_id: sessionId,
    };
    const resp = await fetch(`/s/${slug}/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (resp.status === 200) return await resp.json();
    const err = await resp.json();
    if (err.detail === "invalid_submission") {
      showOnlyTitle("本次答题未通过有效性校验");
      return null;
    }
    const msg = { already_submitted: "您已填写过本问卷，感谢参与。",
                  token_used: "该链接已被使用。", token_expired: "问卷已关闭。",
                  token_not_found: "链接无效。" }[err.detail] || "提交失败，请稍后再试。";
    showResult(msg, "#d4380d");
    if (err.detail === "already_submitted") { hideForm(); showRedeemAction(); }
    else setActionsDisabled(false);
    return null;
  }

  // 「提交问卷」：提交后结束，展示兑换码与去兑奖按钮。
  async function submitTier1Only() {
    const extra = await askDegree();   // 提交问卷 → 先弹度数 → 填写完成后才提交
    track("submit", { tier: 1, question_id: stepCurrentId, dwell_ms: questionDwellMs() });
    const data = await postTier1(extra);
    if (!data) return;
    hideForm();
    const code1 = data.display_code || data.redeem_code;
    showCodeResult('<p>提交成功！你将获得 M 系列 2 片装。点「去兑奖」会自动复制兑换码并前往下单，请在订单备注中粘贴。</p>', code1);
    showRedeemAction(code1);
  }

  function completeTier1ByRoute() {
    if (!tier2.length || !stepAnswers.q3 || stepAnswers.q3 === ONLY_BEAUTY) submitTier1Only();
    else submitTier1AndContinue();
  }

  // 「继续作答」：提交 Tier 1 后直接进入 Tier 2。
  async function submitTier1AndContinue() {
    track("continue", { question_id: stepCurrentId, dwell_ms: questionDwellMs() });
    const data = await postTier1();
    if (!data) return;
    startTier2();
  }

  // 进入 Tier 2 逐题作答。
  function startTier2() {
    beginTier(tier2, "tier2");
  }

  // Tier 2 升级提交。
  async function submitTier2() {
    const extra = await askDegree();   // 提交并升级 → 先弹度数 → 填写完成后才提交
    track("upgrade", {});
    setActionsDisabled(true);
    const resp = await fetch(`/s/${slug}/upgrade`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fingerprint,
        answers: Object.assign({}, visibleAnswers(), extra || {}),
        elapsed_ms: Date.now() - startedAt,
        session_id: sessionId,
      }),
    });
    if (resp.status === 200) {
      const data = await resp.json();
      hideForm();
      const code2 = data.display_code || data.redeem_code;
      showCodeResult('<p>提交成功！你将获得 M 系列 10 片装。点「去兑奖」会自动复制兑换码并前往下单，请在订单备注中粘贴。</p>', code2);
      showRedeemAction(code2);
    } else {
      const error = await resp.json().catch(function () { return {}; });
      if (error.detail === "invalid_submission") showOnlyTitle("本次答题未通过有效性校验");
      else showResult("提交失败，请稍后再试。", "#d4380d");
      setActionsDisabled(false);
    }
  }

  async function init() {
    attachSwipeNavigation();
    attachSideArrowNavigation();
    attachRulesPanel();
    if (isFilePreview) {
      document.body.classList.add("file-preview");
      document.getElementById("title").textContent = "moody 用户调研问卷";
      schema = FILE_PREVIEW_SCHEMA;
      splitTiers(schema);
      beginTier(tier1, "tier1");
      return;
    }
    fingerprint = await getFingerprint();
    function fetchSurveyData() {
      let url = `/api/s/${slug}?c=${encodeURIComponent(channel)}&fp=${encodeURIComponent(fingerprint)}`;
      if (aid) url += `&aid=${encodeURIComponent(aid)}`;
      if (token) url += `&t=${encodeURIComponent(token)}`;
      return fetch(url);
    }
    let resp = await fetchSurveyData();
    if (resp.status !== 200) {
      document.getElementById("title").textContent = "问卷不存在或已关闭";
      return;
    }
    let data = await resp.json();
    // 通用链接首开/重开：后端按设备发回 token → 原地换 token 页内重拉，
    // 不整页刷新（避免空白底图过渡 + 白屏闪烁），地址栏仍写入 t= 保留刷新/分享语义
    if (data.token_status === "claim" && data.token) {
      token = data.token;
      try {
        const u = new URL(location.href);
        u.searchParams.set("t", token);
        history.replaceState(null, "", u.toString());
      } catch (e) { /* 忽略 */ }
      resp = await fetchSurveyData();
      if (resp.status !== 200) {
        document.getElementById("title").textContent = "问卷不存在或已关闭";
        return;
      }
      data = await resp.json();
    }
    document.getElementById("title").textContent = data.title;
    newProductUrl = data.new_product_url || "";
    schema = data.schema || [];
    splitTiers(schema);
    // 已提交但只到基础层且还有进阶题 → 重进续答进阶，而不是锁死在兑奖码页
    const resumeTier2 = data.token_status === "submitted_self" && data.submitted_tier === 1 &&
      data.can_resume_tier2 === true && tier2.length > 0;

    // 页面浏览：value 记落地页类型，后台直接看到访客落在了什么页
    const landing = resumeTier2 ? "答题页(进阶续答)" : ({
      ended: "活动结束页", ineligible: "无资格页", expired: "问卷已关闭页",
      used: "链接已被使用页", not_found: "链接无效页", submitted_self: "兑奖码页",
    }[data.token_status] || "答题页");
    track("page_view", { value: landing });

    // 活动结束 / 无资格 / 旧链接失效
    if (data.token_status === "ended") { showOnlyTitle("本次活动已结束"); return; }
    if (data.token_status === "ineligible") { showOnlyTitle("无资格", "ineligible"); return; }
    if (data.token_status === "expired" || data.token_status === "used") {
      showOnlyTitle(data.token_status === "expired" ? "问卷已关闭" : "该链接已被使用");
      return;
    }
    if (data.token_status === "not_found") { showOnlyTitle("链接无效"); return; }
    if (data.token_status === "invalid_submission") { showOnlyTitle("本次答题未通过有效性校验"); return; }

    // 本人重开：进阶没答完 → 续答进阶；否则停留兑换码页（重现真实码）
    if (resumeTier2) { startTier2(); return; }
    if (data.token_status === "submitted_self") {
      hideForm();
      const code = data.display_code || "";
      const prize = data.submitted_tier >= 2 ? "M 系列 10 片装" : "M 系列 2 片装";
      if (code) { showCodeResult('<p>您已完成问卷，将获得 ' + prize + '。点「去兑奖」会自动复制兑换码并前往下单。</p>', code); }
      else { showResult("您已填写过本问卷，感谢参与。"); }
      showRedeemAction(code);
      return;
    }

    // 有资格：把 user_code 写进地址栏（展示用，幂等）
    if (data.user_code && token) {
      try {
        var u = new URL(location.href);
        if (!u.searchParams.get("uc")) {
          u.searchParams.set("uc", data.user_code);
          history.replaceState(null, "", u.toString());
        }
      } catch (e) { /* 忽略 */ }
    }

    // 重进续答：已达 Tier 1 且有 Tier 2 题 → 直接进入 Tier 2
    if (data.submitted_tier === 1 && tier2.length > 0) { startTier2(); return; }
    if (data.submitted_tier >= 2) {
      showOnlyTitle(data.title);
      showResult("您已完成全部问卷，感谢参与。");
      showRedeemAction();
      return;
    }
    beginTier(tier1, "tier1");
  }

  // ===== 画布宽度冻结（Pura X 等键盘弹出适配）=====
  // HarmonyOS/Android WebView 弹出键盘会压缩布局视口高度，CSS 里 100vh/100svh 驱动的
  // --canvas-width 随之坍缩，整页挤变形。JS 把画布宽度冻结为像素值：
  // 仅视口宽度变化（转屏/折叠/分屏）时重算，纯高度变化（键盘弹出收起）忽略。
  function lockCanvasWidth() {
    const w = Math.min(window.innerWidth, window.innerHeight * 941 / 1672, 640);
    document.documentElement.style.setProperty("--canvas-width", w.toFixed(1) + "px");
  }
  let lockedViewportWidth = window.innerWidth;
  window.addEventListener("resize", function () {
    if (window.innerWidth === lockedViewportWidth) return; // 键盘只变高度 → 忽略
    lockedViewportWidth = window.innerWidth;
    lockCanvasWidth();
    settleArtworkLayout();
  });
  lockCanvasWidth();

  init();
})();
