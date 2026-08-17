(() => {
  const SLUG = "moody";
  const DEVICE_KEY = "moody-survey-fastapi-device";
  const TOKEN_KEY = "moody-survey-fastapi-token";
  const startedAt = Date.now();
  const sessionId = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  const params = new URLSearchParams(location.search);
  const channel = params.get("c") || "unknown";
  const aid = params.get("aid") || "";
  let token = params.get("t") || localStorage.getItem(TOKEN_KEY) || "";
  let serverSchema = [];
  let productUrl = "https://detail.tmall.com/item.htm?id=1072972797956";

  const serverIds = {
    q1: "q1", q2: "q2", q3: "q3",
    q4a: "q4_only", q5a: "q5_only", q6a: "q6_only",
    q4b: "q4_cycle", q5b: "q5_scene", q6b: "q6_purchase",
    q7b1: "q7_products", q8b1: "q8_purchase_reason", q9b1: "q9_other_brands", q10b1: "q10_satisfied",
    q7b2: "q7_lapsed_reason", q8b2: "q8_stop_reason", q9b2: "q9_return",
    q7b3: "q7_never_reason", q8b3: "q8_daily_brands", q9b3: "q9_brand_reason", q10b3: "q10_first_purchase",
    q11: "q11_price", q12: "q12_premium", q13: "q13_channel", q14: "q14_content",
    degree: "q_degree"
  };

  const getFingerprint = () => {
    let value = localStorage.getItem(DEVICE_KEY);
    if (!value) {
      value = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}-${Math.random()}`;
      localStorage.setItem(DEVICE_KEY, value);
    }
    return value;
  };
  const fingerprint = getFingerprint();

  const statusStyles = document.createElement("style");
  statusStyles.textContent = `
    .status-card-v2{position:absolute;z-index:3;left:13.8%;top:36.6%;width:72.4%;min-height:18.6%;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:8% 6% 6%;border:1.5px solid #f0c28b;border-radius:28px;background:#fffdf9;box-shadow:0 10px 28px #9d57161c;color:#4b2c1d}
    .status-badge-v2{position:absolute;left:50%;top:0;transform:translate(-50%,-50%);width:13%;aspect-ratio:1;border:5px solid #fff3df;border-radius:50%;display:grid;place-items:center;background:#ffb84c;color:#fff;font-family:"Gotham Survey",sans-serif;font-size:clamp(24px,6.5vw,38px);font-weight:900;line-height:1}
    .status-card-v2 h1{margin:0 0 5%;color:#f16624;font-size:clamp(20px,5vw,29px);font-weight:800;line-height:1.3}
    .status-card-v2 p{margin:0;font-size:clamp(12px,2.9vw,16px);font-weight:500;line-height:1.75}
  `;
  document.head.append(statusStyles);

  const api = async (url, options) => {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data.detail || data.error || "网络请求失败";
      const error = new Error(detail);
      error.code = detail;
      throw error;
    }
    return data;
  };

  const surveyUrl = currentToken => {
    const query = new URLSearchParams({fp: fingerprint, c: channel});
    if (currentToken) query.set("t", currentToken);
    if (aid) query.set("aid", aid);
    return `/api/s/${SLUG}?${query}`;
  };

  const rewardPage = (code, tier) => {
    const degree = code.match(/-(\d+)$/)?.[1] || "所选";
    const prize = tier >= 2 ? "M 系列 10 片装" : "M 系列 2 片装";
    return `
      <div class="reward-v2">
        <div class="reward-title" aria-label="moody 老朋友白片探索计划">
          <div class="title-line"><img class="moody-logo" src="assets/moody-logo-original.webp?v=20260817" alt="moody" decoding="async"><span>老朋友</span></div>
          <div><em>白片</em>探索计划</div>
        </div>
        <div class="reward-copy">提交成功！奖品为 ${prize}（${degree} 度）<br>点「去兑奖」将自动复制并前往下单<br>（在订单备注粘贴即可领奖）：</div>
        <div class="reward-code" id="code">${code}</div>
        <button class="reward-redeem" id="redeem" type="button"><span class="reward-redeem-label">去兑奖 <span aria-hidden="true">→</span></span></button>
        <section class="reward-instructions" aria-labelledby="reward-notes-title">
          <img class="reward-notes-star" src="assets/reward-notes-star.png" alt="">
          <h2 id="reward-notes-title">使用说明</h2>
          <ol>
            <li><span>点「去兑奖」会自动复制兑换码并前往天猫店铺。</span></li>
            <li><span>下单时在订单备注中粘贴兑换码，即可领取对应奖品。</span></li>
            <li><span>每台设备和每个 IP 仅可参与一次，每个码仅可核销一次。</span></li>
          </ol>
        </section>
      </div>`;
  };

  const statusPage = (title, copy) => `
    <div class="reward-v2 status-v2">
      <div class="reward-title" aria-label="moody 老朋友白片探索计划">
        <div class="title-line"><img class="moody-logo" src="assets/moody-logo-original.webp?v=20260817" alt="moody" decoding="async"><span>老朋友</span></div>
        <div><em>白片</em>探索计划</div>
      </div>
      <section class="status-card-v2"><div class="status-badge-v2" aria-hidden="true">!</div><h1>${title}</h1><p>${copy}</p></section>
    </div>`;

  const showStatus = (title, copy) => {
    screen.className = "shell reward-shell";
    screen.innerHTML = statusPage(title, copy);
  };

  const bindRedeem = code => document.querySelector("#redeem")?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(code);
      show("兑换码已复制，即将前往天猫");
    } catch {
      show("请长按复制兑换码，即将前往天猫");
    }
    setTimeout(() => location.assign(productUrl), 350);
  });

  const showReward = (code, tier) => {
    screen.className = "shell reward-shell";
    screen.innerHTML = rewardPage(code, tier);
    bindRedeem(code);
  };

  const initialize = async () => {
    let data = await api(surveyUrl(token));
    if (data.token_status === "claim") {
      token = data.token;
      localStorage.setItem(TOKEN_KEY, token);
      data = await api(surveyUrl(token));
    }
    serverSchema = data.schema || [];
    productUrl = data.new_product_url || productUrl;
    if (data.token) {
      token = data.token;
      localStorage.setItem(TOKEN_KEY, token);
    }
    if (data.token_status === "submitted_self" && data.can_resume_tier2) {
      show("已恢复答题资格，请重新完成问卷后提交");
      return data;
    }
    if (data.token_status === "submitted_self") {
      if (data.submission_status === "redeemed") {
        showStatus("兑换码已核销", "本设备的兑换码已经使用，不能再次兑奖或重复参与。");
      } else {
        showReward(data.display_code, data.submitted_tier || 1);
      }
      return data;
    }
    const blocked = {
      ineligible: ["当前网络已参与过", "为防止重复刷奖品，每台设备和每个 IP 地址只可参与一次。"],
      invalid_submission: ["本次答卷未通过", "答卷触发了质量规则，因此没有生成可使用的兑换码。"],
      ended: ["活动已结束", "感谢关注，本次问卷活动已经结束。"],
      expired: ["问卷链接已过期", "该问卷链接已超过有效期，请联系工作人员。"],
      not_found: ["问卷链接无效", "请检查链接是否完整，或联系工作人员重新获取。"]
    };
    if (blocked[data.token_status]) showStatus(...blocked[data.token_status]);
    return data;
  };

  const ready = initialize().catch(error => {
    showStatus("页面连接失败", `${error.message || "网络连接异常"}，请检查网络后刷新页面。`);
    return {token_status: "error"};
  });

  const translatedAnswers = () => {
    const output = {};
    const serverById = new Map(serverSchema.map(question => [question.id, question]));
    for (const question of qs) {
      const selected = ans[question.id];
      if (!selected?.length) continue;
      const serverId = serverIds[question.id];
      const serverQuestion = serverById.get(serverId);
      if (!serverId || !serverQuestion) continue;
      const values = selected.map(index => {
        let value = serverQuestion.options?.[index] ?? question.o[index];
        if (question.other === index) {
          const text = String(ans[`${question.id}Text`] || "").trim();
          if (text) value = `${value}：${text}`;
        }
        return value;
      });
      output[serverId] = serverQuestion.type === "multi" ? values : values[0];
    }
    return output;
  };

  const requestBody = answers => ({
    fingerprint,
    answers,
    elapsed_ms: Date.now() - startedAt,
    channel,
    token,
    session_id: sessionId,
    device: {viewport: `${innerWidth}x${innerHeight}`, dpr: devicePixelRatio || 1, platform: navigator.platform || ""}
  });

  result = async function submitSurveyToFastApi() {
    window.scrollTo({top: 0, behavior: "smooth"});
    showStatus("正在提交…", "正在保存答卷并生成兑换码，请不要关闭页面。");
    try {
      const survey = await ready;
      if (!["eligible", "submitted_self"].includes(survey.token_status)) return;
      const allAnswers = translatedAnswers();
      const onlyBeauty = allAnswers.q3 === "只戴美瞳";
      if (onlyBeauty) {
        const submitted = await api(`/s/${SLUG}/submit`, {
          method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(requestBody(allAnswers))
        });
        showReward(submitted.display_code, submitted.tier || 1);
        return;
      }
      const tierOne = {q1: allAnswers.q1, q2: allAnswers.q2, q3: allAnswers.q3};
      await api(`/s/${SLUG}/submit`, {
        method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(requestBody(tierOne))
      });
      const upgraded = await api(`/s/${SLUG}/upgrade`, {
        method: "POST", headers: {"content-type": "application/json"},
        body: JSON.stringify({fingerprint, answers: allAnswers, elapsed_ms: Date.now() - startedAt, session_id: sessionId})
      });
      showReward(upgraded.display_code, upgraded.tier || 2);
    } catch (error) {
      const messages = {
        invalid_submission: ["本次答卷未通过", "填写时间过短或答案过于规律，因此没有生成兑换码。答卷仍已保存供数据分析。"],
        already_submitted: ["本设备已参与过", "每台设备和每个 IP 地址只可参与一次。"],
        ineligible: ["当前网络已参与过", "每台设备和每个 IP 地址只可参与一次。"],
        ended: ["活动已结束", "感谢关注，本次问卷活动已经结束。"],
        token_expired: ["问卷链接已过期", "请联系工作人员重新获取链接。"]
      };
      const message = messages[error.code] || ["提交失败", `${error.message || "网络连接异常"}，请检查网络后刷新页面。`];
      showStatus(...message);
    }
  };
})();
