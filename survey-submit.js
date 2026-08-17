(() => {
  const DEVICE_KEY = 'moody-survey-device-id';
  const getDeviceId = () => {
    let id = localStorage.getItem(DEVICE_KEY);
    if (!id) {
      id = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}-${Math.random()}`;
      localStorage.setItem(DEVICE_KEY, id);
    }
    return id;
  };
  const deviceId = getDeviceId();
  const statusStyles = document.createElement('style');
  statusStyles.textContent = `
    .status-card-v2{position:absolute;z-index:3;left:13.8%;top:36.6%;width:72.4%;min-height:18.6%;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:8% 6% 6%;border:1.5px solid #f0c28b;border-radius:28px;background:#fffdf9;box-shadow:0 10px 28px #9d57161c;color:#4b2c1d}
    .status-badge-v2{position:absolute;left:50%;top:0;transform:translate(-50%,-50%);width:13%;aspect-ratio:1;border:5px solid #fff3df;border-radius:50%;display:grid;place-items:center;background:#ffb84c;color:#fff;font-family:"Gotham Survey",sans-serif;font-size:clamp(24px,6.5vw,38px);font-weight:900;line-height:1}
    .status-card-v2 h1{margin:0 0 5%;color:#f16624;font-size:clamp(20px,5vw,29px);font-weight:800;line-height:1.3}
    .status-card-v2 p{margin:0;font-size:clamp(12px,2.9vw,16px);font-weight:500;line-height:1.75}
    .status-retry-v2{width:78%;min-height:44px;margin-top:7%;border:0;border-radius:999px;background:linear-gradient(180deg,#ff963c,#ff6718);box-shadow:0 5px 0 #dc5615;color:#fff;font-family:"Noto Sans SC Survey",sans-serif;font-size:clamp(14px,3.4vw,19px);font-weight:700;cursor:pointer}
    .status-warning .status-badge-v2{background:#ff9c38}
  `;
  document.head.append(statusStyles);
  const surveySession = fetch('/api/sessions', {
    method: 'POST',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify({deviceId})
  }).then(async response => {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || '无法建立答题会话');
      error.code = data.code;
      throw error;
    }
    return data;
  });
  const rewardPage = (code, prizeName, degreeLabel) => `
    <div class="reward-v2">
      <div class="reward-title" aria-label="moody 老朋友白片探索计划">
        <div class="title-line"><img class="moody-logo" src="assets/moody-logo-original.webp?v=20260817" alt="moody" decoding="async"><span>老朋友</span></div>
        <div><em>白片</em>探索计划</div>
      </div>
      <div class="reward-copy">提交成功！奖品为${prizeName || '专属试用装'}（${degreeLabel || '所选度数'}）<br>点击「去兑奖」自动复制并前往天猫<br>（下单时请在订单备注粘贴兑换码）：</div>
      <div class="reward-code" id="code">${code}</div>
      <button class="reward-redeem" id="redeem" type="button"><span class="reward-redeem-label">去兑奖 <span aria-hidden="true">→</span></span></button>
      <section class="reward-instructions" aria-labelledby="reward-notes-title">
        <img class="reward-notes-star" src="assets/reward-notes-star.png" alt="">
        <h2 id="reward-notes-title">使用说明</h2>
        <ol>
          <li><span>点击「去兑奖」会自动复制兑换码。</span></li>
          <li><span>下单时在订单备注中粘贴兑换码，即可领取对应奖励。</span></li>
          <li><span>每台设备仅可领取一个兑换码，每个码仅可兑奖一次。</span></li>
        </ol>
      </section>
    </div>`;
  const statusPage = (title, copy, retry = false, warning = false) => `
    <div class="reward-v2 status-v2 ${retry || warning ? 'status-warning' : ''}">
      <div class="reward-title" aria-label="moody 老朋友白片探索计划">
        <div class="title-line"><img class="moody-logo" src="assets/moody-logo-original.webp?v=20260817" alt="moody" decoding="async"><span>老朋友</span></div>
        <div><em>白片</em>探索计划</div>
      </div>
      <section class="status-card-v2">
        <div class="status-badge-v2" aria-hidden="true">${retry || warning ? '!' : '✓'}</div>
        <h1>${title}</h1><p>${copy}</p>
        ${retry ? '<button class="status-retry-v2" id="retry" type="button">重新填写</button>' : ''}
      </section>
    </div>`;
  const bindCopy = (code, redeemUrl) => document.querySelector('#redeem')?.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(code);
      show(redeemUrl ? '兑换码已复制，即将前往天猫' : '兑换码已复制，兑奖链接待配置');
    } catch {
      show('请长按复制兑换码');
    }
    if (redeemUrl) setTimeout(() => location.assign(redeemUrl), 350);
  });

  surveySession.then(session => {
    if (!session.alreadyParticipated) return;
    screen.className = 'shell reward-shell';
    if (session.rewardStatus === 'redeemed') {
      screen.innerHTML = statusPage('本设备已完成兑奖', '该设备领取的兑换码已经核销，不能重复参与或重复兑奖。');
    } else {
      screen.innerHTML = rewardPage(session.rewardCode, session.prizeName, session.degreeLabel);
      bindCopy(session.rewardCode, session.redeemUrl);
      show('本设备已参与，显示原兑换码');
    }
  }).catch(error => {
    if (error.code !== 'IP_ALREADY_PARTICIPATED') return;
    screen.className = 'shell reward-shell';
    screen.innerHTML = statusPage('当前网络已参与过', '为避免重复刷奖品，每个手机设备和每个 IP 地址仅限参与一次。', false, true);
  });

  result = async function submitSurveyAndRenderReward() {
    window.scrollTo({top: 0, behavior: 'smooth'});
    screen.className = 'shell reward-shell';
    screen.innerHTML = statusPage('正在提交…', '正在保存答卷并生成兑换码，请不要关闭页面。');
    const answerDetails = active().filter(q => ans[q.id]).map(q => ({
      id: q.id,
      question: q.t,
      answerIndexes: ans[q.id],
      answerLabels: ans[q.id].map(index => q.o[index]).filter(Boolean),
      otherText: q.other !== undefined && ans[q.id]?.includes(q.other) ? ans[q.id + 'Text'] || '' : ''
    }));
    try {
      const session = await surveySession;
      if (session.alreadyParticipated) {
        if (session.rewardStatus === 'redeemed') screen.innerHTML = statusPage('本设备已完成兑奖', '该设备领取的兑换码已经核销，不能重复参与或重复兑奖。');
        else { screen.innerHTML = rewardPage(session.rewardCode, session.prizeName, session.degreeLabel); bindCopy(session.rewardCode, session.redeemUrl); }
        return;
      }
      const response = await fetch('/api/submissions', {
        method: 'POST',
        headers: {'content-type': 'application/json'},
        body: JSON.stringify({
          sessionId: session.sessionId,
          deviceId,
          answers: ans,
          answerDetails,
          questionnaireVersion: '2026-08-13'
        })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const error = new Error(data.error || '提交失败');
        error.code = data.code;
        throw error;
      }
      if (!data.accepted) {
        const reasonText = {TOO_FAST:'答题时间少于 5 秒', STRAIGHT_LINE:'所有题目选择完全一致', INCOMPLETE:'答卷不完整'};
        const reasons = (data.reasons || []).map(reason => reasonText[reason] || reason).join('、');
        screen.innerHTML = statusPage('本次答卷未通过', `${reasons || '答卷触发质量规则'}，因此没有生成兑换码。答卷已保存供数据质量分析。`, true);
        document.querySelector('#retry')?.addEventListener('click', () => location.reload());
        return;
      }
      if (data.duplicate && data.rewardStatus === 'redeemed') {
        screen.innerHTML = statusPage('本设备已完成兑奖', '该设备领取的兑换码已经核销，不能重复兑奖。感谢您参与调研。');
        return;
      }
      const code = data.rewardCode;
      screen.innerHTML = rewardPage(code, data.prizeName, data.degreeLabel);
      bindCopy(code, data.redeemUrl);
    } catch (error) {
      if (error.code === 'IP_ALREADY_PARTICIPATED') {
        screen.innerHTML = statusPage('当前网络已参与过', '为避免重复刷奖品，每个手机设备和每个 IP 地址仅限参与一次。', false, true);
        return;
      }
      screen.innerHTML = statusPage('提交失败', `${error.message || '网络连接异常'}。请检查网络后刷新页面重新提交。`, true);
      document.querySelector('#retry')?.addEventListener('click', () => location.reload());
    }
  };
})();
