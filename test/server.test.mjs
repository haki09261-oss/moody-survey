import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createSurveyServer } from '../server.mjs';

test('前三种购买状态的购买契机题包含新增的三个卖点选项', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const question = html.match(/\{id:'q8b1'.*?\},/s)?.[0] || '';
  assert.match(question, /被“新手友好”的卖点打动/);
  assert.match(question, /被“水润”“舒适”等佩戴感受卖点打动/);
  assert.match(question, /被“高透氧”“泪循环”等产品参数\/功能打动/);
});

test('移动端关键图片使用轻量 WebP 资源', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const assets = [
    'universal-survey-background.webp',
    'moody-ip-mobile.webp',
    'q7-product-m-mobile.webp',
    'q7-product-air-mobile.webp',
    'q7-product-s-mobile.webp'
  ];
  for (const asset of assets) assert.match(html, new RegExp(asset.replace('.', '\\.')));
  const totalBytes = assets.reduce((sum, asset) => sum + statSync(new URL(`../assets/${asset}`, import.meta.url)).size, 0);
  assert.ok(totalBytes < 300 * 1024, `关键移动图片总计 ${(totalBytes / 1024).toFixed(0)}KB，应低于 300KB`);
});

test('版本化 WebP 资源返回长期缓存头', async t => {
  const app = await setup();
  t.after(() => new Promise(resolve => app.server.close(resolve)));
  const response = await fetch(`${app.base}/assets/universal-survey-background.webp?v=test`, { method:'HEAD' });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('content-type'), 'image/webp');
  assert.match(response.headers.get('cache-control'), /max-age=31536000, immutable/);
});

async function setup(options = {}) {
  const folder = mkdtempSync(join(tmpdir(), 'moody-survey-'));
  const app = createSurveyServer({
    dbPath: join(folder, 'test.sqlite'),
    adminPassword: 'test-admin-password',
    adminSecret: 'test-admin-secret-with-at-least-32-characters',
    deviceSalt: 'test-device-salt-with-at-least-32-characters',
    ...options
  });
  await new Promise(resolve => app.server.listen(0, '127.0.0.1', resolve));
  const address = app.server.address();
  return { ...app, base: `http://127.0.0.1:${address.port}` };
}

async function jsonRequest(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  return { response, data };
}

async function startSession(app, deviceId) {
  const { response, data } = await jsonRequest(`${app.base}/api/sessions`, {
    method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({ deviceId })
  });
  assert.equal(response.status, 201);
  return data.sessionId;
}

test('有效答卷发唯一码，后台可查询并且只能核销一次', async t => {
  const app = await setup();
  t.after(() => new Promise(resolve => app.server.close(resolve)));
  const deviceId = 'device-valid-00000000000001';
  const sessionId = await startSession(app, deviceId);
  app.db.prepare('UPDATE survey_sessions SET started_at = ? WHERE id = ?').run(Date.now() - 8_000, sessionId);
  const answers = { q1:[0], q2:[1], q3:[0], q4a:[2], q5a:[0], q6a:[3], degree:[8] };
  const answerDetails = Object.entries(answers).map(([id, indexes]) => ({ id, question:`问题 ${id}`, answerIndexes:indexes, answerLabels:[`答案 ${indexes[0]}`] }));
  const submitted = await jsonRequest(`${app.base}/api/submissions`, {
    method:'POST', headers:{'content-type':'application/json'},
    body:JSON.stringify({ sessionId, deviceId, answers, answerDetails })
  });
  assert.equal(submitted.response.status, 201);
  assert.equal(submitted.data.accepted, true);
  assert.match(submitted.data.rewardCode, /^M2-D300-[A-Z0-9]{8}$/);
  assert.equal(submitted.data.prizeName, 'M系列2片装');
  assert.equal(submitted.data.degreeLabel, '300度');
  assert.equal(submitted.data.redeemUrl, 'https://detail.tmall.com/item.htm?id=1072972797956');

  const login = await jsonRequest(`${app.base}/api/admin/login`, {
    method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({password:'test-admin-password'})
  });
  assert.equal(login.response.status, 200);
  const cookie = login.response.headers.get('set-cookie').split(';')[0];
  const listed = await jsonRequest(`${app.base}/api/admin/submissions?search=${submitted.data.rewardCode}`, { headers:{cookie} });
  assert.equal(listed.data.length, 1);
  assert.equal(listed.data[0].answerDetails.length, 7);
  const analytics = await jsonRequest(`${app.base}/api/admin/analytics?days=all`, { headers:{cookie} });
  assert.equal(analytics.response.status, 200);
  assert.equal('insights' in analytics.data, false);
  assert.equal(analytics.data.summary.total, 1);
  assert.equal(analytics.data.summary.validRate, 1);
  assert.equal(analytics.data.rewards[0].name, 'M系列2片装');
  assert.equal(analytics.data.questions.length, 7);

  const redeemUrl = `${app.base}/api/admin/rewards/${submitted.data.rewardCode}/redeem`;
  const redeemed = await jsonRequest(redeemUrl, {
    method:'POST', headers:{'content-type':'application/json',cookie}, body:JSON.stringify({staffName:'测试员工',note:'自动化测试'})
  });
  assert.equal(redeemed.response.status, 200);
  const repeated = await jsonRequest(redeemUrl, {
    method:'POST', headers:{'content-type':'application/json',cookie}, body:JSON.stringify({staffName:'测试员工'})
  });
  assert.equal(repeated.response.status, 409);
  assert.match(repeated.data.error, /已经核销/);

  const exported = await fetch(`${app.base}/api/admin/export.csv`, { headers:{cookie} });
  assert.equal(exported.status, 200);
  assert.match(await exported.text(), /测试员工/);
});

test('少于五秒和全部相同分别标记异常且不发码', async t => {
  const app = await setup();
  t.after(() => new Promise(resolve => app.server.close(resolve)));
  const fastDevice = 'device-fast-0000000000000001';
  const fastSession = await startSession(app, fastDevice);
  const varied = { q1:[0], q2:[1], q3:[0], q4a:[2], q5a:[0], q6a:[3], degree:[3] };
  const fast = await jsonRequest(`${app.base}/api/submissions`, {
    method:'POST', headers:{'content-type':'application/json'},
    body:JSON.stringify({sessionId:fastSession,deviceId:fastDevice,answers:varied})
  });
  assert.equal(fast.data.accepted, false);
  assert.deepEqual(fast.data.reasons, ['TOO_FAST']);
  assert.equal(fast.data.rewardCode, null);

  const lineDevice = 'device-line-0000000000000001';
  const lineSession = await startSession(app, lineDevice);
  app.db.prepare('UPDATE survey_sessions SET started_at = ? WHERE id = ?').run(Date.now() - 8_000, lineSession);
  const same = { q1:[0], q2:[0], q3:[0], q4a:[0], q5a:[0], q6a:[0], degree:[0] };
  const straight = await jsonRequest(`${app.base}/api/submissions`, {
    method:'POST', headers:{'content-type':'application/json'},
    body:JSON.stringify({sessionId:lineSession,deviceId:lineDevice,answers:same})
  });
  assert.equal(straight.data.accepted, false);
  assert.deepEqual(straight.data.reasons, ['STRAIGHT_LINE']);
  assert.equal(straight.data.rewardCode, null);
});

test('同设备返回原奖码，同 IP 的其他设备被拦截', async t => {
  const app = await setup();
  t.after(() => new Promise(resolve => app.server.close(resolve)));
  const firstDevice = 'device-first-000000000000001';
  const sessionId = await startSession(app, firstDevice);
  app.db.prepare('UPDATE survey_sessions SET started_at = ? WHERE id = ?').run(Date.now() - 8_000, sessionId);
  const answers = { q1:[0], q2:[1], q3:[0], q4a:[2], q5a:[0], q6a:[3], degree:[8] };
  const first = await jsonRequest(`${app.base}/api/submissions`, {
    method:'POST', headers:{'content-type':'application/json'},
    body:JSON.stringify({sessionId,deviceId:firstDevice,answers})
  });
  assert.equal(first.response.status, 201);

  const sameDevice = await jsonRequest(`${app.base}/api/sessions`, {
    method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({deviceId:firstDevice})
  });
  assert.equal(sameDevice.response.status, 200);
  assert.equal(sameDevice.data.alreadyParticipated, true);
  assert.equal(sameDevice.data.rewardCode, first.data.rewardCode);

  const secondDevice = await jsonRequest(`${app.base}/api/sessions`, {
    method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({deviceId:'device-second-00000000000001'})
  });
  assert.equal(secondDevice.response.status, 409);
  assert.equal(secondDevice.data.code, 'IP_ALREADY_PARTICIPATED');

  const login = await jsonRequest(`${app.base}/api/admin/login`, {
    method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({password:'test-admin-password'})
  });
  const cookie = login.response.headers.get('set-cookie').split(';')[0];
  const analytics = await jsonRequest(`${app.base}/api/admin/analytics`, {headers:{cookie}});
  assert.equal(analytics.data.summary.blockedAttempts, 2);
  assert.equal(analytics.data.summary.blockedIp, 1);
  assert.equal(analytics.data.summary.blockedDevice, 1);
});

test('测试模式允许同设备同 IP 重复提交并在后台单独标记', async t => {
  const app = await setup({ testMode: true });
  t.after(() => new Promise(resolve => app.server.close(resolve)));
  const deviceId = 'device-test-mode-000000000001';
  const answers = { q1:[0], q2:[1], q3:[0], q4a:[2], q5a:[0], q6a:[3], degree:[8] };
  const codes = [];
  for (let index = 0; index < 2; index += 1) {
    const sessionId = await startSession(app, deviceId);
    app.db.prepare('UPDATE survey_sessions SET started_at = ? WHERE id = ?').run(Date.now() - 8_000, sessionId);
    const submitted = await jsonRequest(`${app.base}/api/submissions`, {
      method:'POST', headers:{'content-type':'application/json'},
      body:JSON.stringify({sessionId,deviceId,answers})
    });
    assert.equal(submitted.response.status, 201);
    assert.equal(submitted.data.isTest, true);
    codes.push(submitted.data.rewardCode);
  }
  assert.notEqual(codes[0], codes[1]);

  const login = await jsonRequest(`${app.base}/api/admin/login`, {
    method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({password:'test-admin-password'})
  });
  const cookie = login.response.headers.get('set-cookie').split(';')[0];
  const testRows = await jsonRequest(`${app.base}/api/admin/submissions?scope=test`, {headers:{cookie}});
  const formalRows = await jsonRequest(`${app.base}/api/admin/submissions?scope=formal`, {headers:{cookie}});
  const analytics = await jsonRequest(`${app.base}/api/admin/analytics?scope=test`, {headers:{cookie}});
  assert.equal(testRows.data.length, 2);
  assert.ok(testRows.data.every(row => row.isTest));
  assert.equal(formalRows.data.length, 0);
  assert.equal(analytics.data.summary.testCount, 2);
});

test('两种都戴路径必须完成全部题目并发放 M 系列 10 片装', async t => {
  const app = await setup();
  t.after(() => new Promise(resolve => app.server.close(resolve)));
  const deviceId = 'device-m10-00000000000000001';
  const sessionId = await startSession(app, deviceId);
  app.db.prepare('UPDATE survey_sessions SET started_at = ? WHERE id = ?').run(Date.now() - 12_000, sessionId);
  const answers = {
    q1:[0], q2:[1], q3:[1], q4b:[2], q5b:[3], q6b:[2],
    q7b2:[0], q8b2:[1], q9b2:[2], q11:[3], q12:[4], q13:[5], q14:[0], degree:[17]
  };
  const incomplete = await jsonRequest(`${app.base}/api/submissions`, {
    method:'POST', headers:{'content-type':'application/json'},
    body:JSON.stringify({sessionId,deviceId,answers:{...answers,q14:undefined}})
  });
  assert.equal(incomplete.data.accepted, false);
  assert.ok(incomplete.data.reasons.includes('INCOMPLETE'));

  const completeSessionId = await startSession(app, deviceId);
  app.db.prepare('UPDATE survey_sessions SET started_at = ? WHERE id = ?').run(Date.now() - 12_000, completeSessionId);
  const submitted = await jsonRequest(`${app.base}/api/submissions`, {
    method:'POST', headers:{'content-type':'application/json'},
    body:JSON.stringify({sessionId:completeSessionId,deviceId,answers})
  });
  assert.equal(submitted.response.status, 201);
  assert.equal(submitted.data.accepted, true);
  assert.equal(submitted.data.prizeName, 'M系列10片装');
  assert.equal(submitted.data.degreeLabel, '525度');
  assert.equal(submitted.data.redeemUrl, 'https://detail.tmall.com/item.htm?id=1072972797956');
  assert.match(submitted.data.rewardCode, /^M10-D525-[A-Z0-9]{8}$/);
});

test('第十二题其他内容限制 100 字且空内容判定为不完整', async t => {
  const app = await setup({ testMode: true });
  t.after(() => new Promise(resolve => app.server.close(resolve)));
  const deviceId = 'device-q12-other-0000000000001';
  const baseAnswers = {
    q1:[0], q2:[1], q3:[1], q4b:[2], q5b:[3], q6b:[2],
    q7b2:[2,3,4], q8b2:[1], q9b2:[2], q11:[3], q12:[5], q13:[5], q14:[0], degree:[6]
  };

  const validSessionId = await startSession(app, deviceId);
  app.db.prepare('UPDATE survey_sessions SET started_at = ? WHERE id = ?').run(Date.now() - 12_000, validSessionId);
  const longText = '测'.repeat(120);
  const submitted = await jsonRequest(`${app.base}/api/submissions`, {
    method:'POST', headers:{'content-type':'application/json'},
    body:JSON.stringify({
      sessionId:validSessionId,
      deviceId,
      answers:{...baseAnswers,q12Text:longText},
      answerDetails:[{id:'q12',question:'你愿意因为什么接受更高价格？',answerIndexes:[5],answerLabels:['其他'],otherText:longText}]
    })
  });
  assert.equal(submitted.data.accepted, true);
  const saved = app.db.prepare('SELECT answers_json, answer_details_json FROM submissions WHERE session_id = ?').get(validSessionId);
  assert.equal(JSON.parse(saved.answers_json).q12Text.length, 100);
  assert.equal(JSON.parse(saved.answer_details_json)[0].otherText.length, 100);

  const emptySessionId = await startSession(app, deviceId);
  app.db.prepare('UPDATE survey_sessions SET started_at = ? WHERE id = ?').run(Date.now() - 12_000, emptySessionId);
  const incomplete = await jsonRequest(`${app.base}/api/submissions`, {
    method:'POST', headers:{'content-type':'application/json'},
    body:JSON.stringify({sessionId:emptySessionId,deviceId,answers:{...baseAnswers,q12Text:''}})
  });
  assert.equal(incomplete.data.accepted, false);
  assert.ok(incomplete.data.reasons.includes('INCOMPLETE'));
});
