import { createServer } from 'node:http';
import { createReadStream, existsSync, mkdirSync, statSync } from 'node:fs';
import { dirname, extname, join, normalize, resolve, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createHash, createHmac, randomBytes, timingSafeEqual } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';

const ROOT = dirname(fileURLToPath(import.meta.url));
const FIVE_SECONDS_MS = 5_000;
const ADMIN_COOKIE = 'survey_admin';
const DEFAULT_TMALL_REDEEM_URL = 'https://detail.tmall.com/item.htm?id=1072972797956';
const MIME = {
  '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
  '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.otf': 'font/otf'
};

function json(res, status, body, headers = {}) {
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', ...headers });
  res.end(JSON.stringify(body));
}

function readBody(req, maxBytes = 256 * 1024) {
  return new Promise((resolveBody, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', chunk => {
      size += chunk.length;
      if (size > maxBytes) {
        reject(Object.assign(new Error('请求内容过大'), { statusCode: 413 }));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => {
      try { resolveBody(chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : {}); }
      catch { reject(Object.assign(new Error('JSON 格式错误'), { statusCode: 400 })); }
    });
    req.on('error', reject);
  });
}

function hash(value, salt) {
  return createHash('sha256').update(`${salt}:${value}`).digest('hex');
}

function safeEqual(a, b) {
  const left = Buffer.from(String(a));
  const right = Buffer.from(String(b));
  return left.length === right.length && timingSafeEqual(left, right);
}

function cookieMap(req) {
  return Object.fromEntries((req.headers.cookie || '').split(';').map(v => v.trim()).filter(Boolean).map(v => {
    const index = v.indexOf('=');
    return [decodeURIComponent(v.slice(0, index)), decodeURIComponent(v.slice(index + 1))];
  }));
}

function signAdminToken(secret) {
  const payload = Buffer.from(JSON.stringify({ exp: Date.now() + 8 * 60 * 60 * 1000 })).toString('base64url');
  const signature = createHmac('sha256', secret).update(payload).digest('base64url');
  return `${payload}.${signature}`;
}

function validAdminToken(token, secret) {
  try {
    const [payload, signature] = String(token || '').split('.');
    if (!payload || !safeEqual(signature, createHmac('sha256', secret).update(payload).digest('base64url'))) return false;
    return JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')).exp > Date.now();
  } catch { return false; }
}

function requestIp(req, trustProxy) {
  const source = trustProxy ? req.headers['x-forwarded-for'] || req.socket.remoteAddress : req.socket.remoteAddress;
  return String(source || '').split(',')[0].trim().slice(0, 80);
}

function sanitizeAnswers(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Object.assign(new Error('答卷格式错误'), { statusCode: 400 });
  const output = {};
  for (const [key, raw] of Object.entries(value).slice(0, 80)) {
    if (!/^[a-zA-Z0-9_-]{1,40}(Text)?$/.test(key)) continue;
    if (Array.isArray(raw)) output[key] = raw.slice(0, 20).map(Number).filter(Number.isFinite);
    else if (typeof raw === 'string') output[key] = raw.trim().slice(0, key === 'q12Text' ? 100 : 500);
  }
  return output;
}

function sanitizeAnswerDetails(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 80).map(item => ({
    id: String(item?.id || '').slice(0, 40),
    question: String(item?.question || '').slice(0, 500),
    answerIndexes: Array.isArray(item?.answerIndexes) ? item.answerIndexes.slice(0, 20).map(Number).filter(Number.isFinite) : [],
    answerLabels: Array.isArray(item?.answerLabels) ? item.answerLabels.slice(0, 20).map(x => String(x).slice(0, 500)) : [],
    otherText: String(item?.otherText || '').slice(0, item?.id === 'q12' ? 100 : 500)
  })).filter(item => item.id && item.question);
}

function requiredQuestionIds(answers) {
  if (answers.q3?.includes(0)) return ['q1','q2','q3','q4a','q5a','q6a','degree'];
  if (!answers.q3?.some(value => value === 1 || value === 2)) return [];
  const common = ['q1','q2','q3','q4b','q5b','q6b'];
  const tail = ['q11','q12','q13','q14','degree'];
  if (answers.q6b?.some(value => value < 2)) return [...common,'q7b1','q8b1','q9b1','q10b1',...tail];
  if (answers.q6b?.includes(2)) return [...common,'q7b2','q8b2','q9b2',...tail];
  if (answers.q6b?.includes(3)) return [...common,'q7b3','q8b3','q9b3','q10b3',...tail];
  return [];
}

function prizeForAnswers(answers, urls = {}) {
  const degreeValues = [100,125,150,175,200,225,250,275,300,325,350,375,400,425,450,475,500,525,550,575,600,650,700,750,800,850,900,950,1000];
  const degreeIndex = answers.degree?.length === 1 ? Number(answers.degree[0]) : NaN;
  if (!Number.isInteger(degreeIndex) || degreeIndex < 0 || degreeIndex >= degreeValues.length) return null;
  const degree = degreeValues[degreeIndex];
  if (answers.q3?.includes(0)) return { sku: 'M_SERIES_2PCS', name: 'M系列2片装', codePrefix: 'M2', degree, degreeLabel: `${degree}度`, redeemUrl: urls.m2 || '' };
  if (answers.q3?.some(value => value === 1 || value === 2)) return { sku: 'M_SERIES_10PCS', name: 'M系列10片装', codePrefix: 'M10', degree, degreeLabel: `${degree}度`, redeemUrl: urls.m10 || '' };
  return null;
}

function antiCheatReasons(answers, durationMs) {
  const reasons = [];
  if (durationMs < FIVE_SECONDS_MS) reasons.push('TOO_FAST');
  const comparable = Object.entries(answers)
    .filter(([key, value]) => key !== 'degree' && !key.endsWith('Text') && Array.isArray(value) && value.length)
    .map(([, value]) => JSON.stringify([...value].sort((a, b) => a - b)));
  if (comparable.length >= 5 && new Set(comparable).size === 1) reasons.push('STRAIGHT_LINE');
  const required = requiredQuestionIds(answers);
  if (!required.length || required.some(id => !Array.isArray(answers[id]) || !answers[id].length)) reasons.push('INCOMPLETE');
  if (answers.q12?.includes(5) && !String(answers.q12Text || '').trim() && !reasons.includes('INCOMPLETE')) reasons.push('INCOMPLETE');
  return reasons;
}

function rewardCode(db, prize) {
  for (let i = 0; i < 10; i += 1) {
    const body = randomBytes(5).toString('base64url').toUpperCase().replace(/[-_]/g, '').slice(0, 8).padEnd(8, 'X');
    const code = `${prize.codePrefix}-D${prize.degree}-${body}`;
    if (!db.prepare('SELECT 1 FROM submissions WHERE reward_code = ?').get(code)) return code;
  }
  throw new Error('无法生成唯一兑换码');
}

function csvCell(value) {
  let text = value == null ? '' : String(value);
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

function setupDatabase(path) {
  mkdirSync(dirname(path), { recursive: true });
  const db = new DatabaseSync(path);
  db.exec(`
    PRAGMA journal_mode = WAL;
    PRAGMA foreign_keys = ON;
    CREATE TABLE IF NOT EXISTS survey_sessions (
      id TEXT PRIMARY KEY, device_hash TEXT NOT NULL, started_at INTEGER NOT NULL,
      ip_hash TEXT, user_agent TEXT
    );
    CREATE TABLE IF NOT EXISTS submissions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      session_id TEXT NOT NULL UNIQUE,
      device_hash TEXT NOT NULL,
      submitted_at INTEGER NOT NULL,
      duration_ms INTEGER NOT NULL,
      status TEXT NOT NULL CHECK(status IN ('valid','invalid')),
      cheat_reasons TEXT NOT NULL DEFAULT '[]',
      answers_json TEXT NOT NULL,
      answer_details_json TEXT NOT NULL DEFAULT '[]',
      questionnaire_version TEXT NOT NULL,
      reward_code TEXT UNIQUE,
      prize_sku TEXT,
      prize_name TEXT,
      degree_label TEXT,
      redeem_url TEXT,
      reward_status TEXT NOT NULL CHECK(reward_status IN ('none','issued','redeemed')),
      redeemed_at INTEGER,
      redeemed_by TEXT,
      staff_note TEXT,
      is_test INTEGER NOT NULL DEFAULT 0,
      ip_hash TEXT,
      user_agent TEXT,
      FOREIGN KEY(session_id) REFERENCES survey_sessions(id)
    );
    CREATE TABLE IF NOT EXISTS anti_abuse_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_type TEXT NOT NULL CHECK(event_type IN ('duplicate_device','duplicate_ip')),
      created_at INTEGER NOT NULL,
      device_hash TEXT,
      ip_hash TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_submissions_status_time ON submissions(status, submitted_at DESC);
    CREATE INDEX IF NOT EXISTS idx_submissions_reward ON submissions(reward_code);
    CREATE INDEX IF NOT EXISTS idx_submissions_device ON submissions(device_hash);
    CREATE INDEX IF NOT EXISTS idx_anti_abuse_time ON anti_abuse_events(created_at DESC);
  `);
  const columns = new Set(db.prepare('PRAGMA table_info(submissions)').all().map(column => column.name));
  for (const [name, definition] of [
    ['prize_sku', 'TEXT'], ['prize_name', 'TEXT'], ['degree_label', 'TEXT'], ['redeem_url', 'TEXT'],
    ['is_test', 'INTEGER NOT NULL DEFAULT 0']
  ]) {
    if (!columns.has(name)) db.exec(`ALTER TABLE submissions ADD COLUMN ${name} ${definition}`);
  }
  db.exec(`
    CREATE UNIQUE INDEX IF NOT EXISTS uniq_valid_submission_device ON submissions(device_hash) WHERE status = 'valid';
    CREATE UNIQUE INDEX IF NOT EXISTS uniq_valid_submission_ip ON submissions(ip_hash) WHERE status = 'valid';
  `);
  return db;
}

function publicSubmission(row, duplicate = false) {
  return {
    submissionId: row.id,
    accepted: row.status === 'valid',
    status: row.status,
    reasons: JSON.parse(row.cheat_reasons || '[]'),
    rewardCode: row.reward_code,
    rewardStatus: row.reward_status,
    prizeSku: row.prize_sku,
    prizeName: row.prize_name,
    degreeLabel: row.degree_label,
    redeemUrl: row.redeem_url,
    isTest: Boolean(row.is_test),
    duplicate
  };
}

const REASON_LABELS = { TOO_FAST: '少于 5 秒', STRAIGHT_LINE: '全部选择一致', INCOMPLETE: '答卷不完整' };
const QUESTION_ORDER = [
  'q1', 'q2', 'q3',
  'q4a', 'q5a', 'q6a',
  'q4b', 'q5b', 'q6b', 'q7b1', 'q7b2', 'q8b1', 'q8b2',
  'q9', 'q10', 'q11', 'q12', 'q13', 'q14', 'q15', 'degree'
];

function dayKey(timestamp) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(timestamp));
}

function buildAnalytics(rows, blockedEvents, scope) {
  const total = rows.length;
  const valid = rows.filter(row => row.status === 'valid').length;
  const invalid = total - valid;
  const testCount = rows.filter(row => row.is_test).length;
  const formalCount = total - testCount;
  const issued = rows.filter(row => row.reward_status === 'issued').length;
  const redeemed = rows.filter(row => row.reward_status === 'redeemed').length;
  const rewardEligible = issued + redeemed;
  const averageDurationSeconds = total ? rows.reduce((sum, row) => sum + row.duration_ms, 0) / total / 1000 : 0;

  const reasonCounts = new Map();
  const rewardCounts = new Map();
  const degreeCounts = new Map();
  const dayCounts = new Map();
  const questionMap = new Map();
  for (const row of rows) {
    for (const reason of JSON.parse(row.cheat_reasons || '[]')) reasonCounts.set(reason, (reasonCounts.get(reason) || 0) + 1);
    if (row.prize_name) {
      const reward = rewardCounts.get(row.prize_name) || { name: row.prize_name, total: 0, issued: 0, redeemed: 0 };
      reward.total += 1;
      if (row.reward_status === 'issued') reward.issued += 1;
      if (row.reward_status === 'redeemed') reward.redeemed += 1;
      rewardCounts.set(row.prize_name, reward);
    }
    if (row.degree_label) degreeCounts.set(row.degree_label, (degreeCounts.get(row.degree_label) || 0) + 1);
    const day = dayKey(row.submitted_at);
    const daily = dayCounts.get(day) || { date: day, total: 0, valid: 0, invalid: 0 };
    daily.total += 1;
    daily[row.status] += 1;
    dayCounts.set(day, daily);
    for (const detail of JSON.parse(row.answer_details_json || '[]')) {
      if (!detail?.id || !detail?.question) continue;
      const question = questionMap.get(detail.id) || { id: detail.id, question: detail.question, respondents: 0, options: new Map() };
      question.respondents += 1;
      for (const label of new Set((detail.answerLabels || []).filter(Boolean))) question.options.set(label, (question.options.get(label) || 0) + 1);
      questionMap.set(detail.id, question);
    }
  }

  const reasons = [...reasonCounts].map(([key, count]) => ({ key, label: REASON_LABELS[key] || key, count, share: invalid ? count / invalid : 0 })).sort((a, b) => b.count - a.count);
  const rewards = [...rewardCounts.values()].map(item => ({ ...item, share: rewardEligible ? item.total / rewardEligible : 0 })).sort((a, b) => b.total - a.total);
  const degrees = [...degreeCounts].map(([label, count]) => ({ label, count, share: rewardEligible ? count / rewardEligible : 0 })).sort((a, b) => Number.parseInt(a.label) - Number.parseInt(b.label));
  const timeline = [...dayCounts.values()].sort((a, b) => a.date.localeCompare(b.date)).slice(-60);
  const questions = [...questionMap.values()].map(question => ({
    id: question.id,
    question: question.question,
    respondents: question.respondents,
    options: [...question.options].map(([label, count]) => ({ label, count, share: question.respondents ? count / question.respondents : 0 })).sort((a, b) => b.count - a.count)
  })).sort((a, b) => {
    const aIndex = QUESTION_ORDER.indexOf(a.id);
    const bIndex = QUESTION_ORDER.indexOf(b.id);
    return (aIndex < 0 ? Number.MAX_SAFE_INTEGER : aIndex) - (bIndex < 0 ? Number.MAX_SAFE_INTEGER : bIndex)
      || a.id.localeCompare(b.id, undefined, { numeric: true });
  });

  return {
    generatedAt: Date.now(), scope,
    summary: {
      total, valid, invalid, testCount, formalCount, validRate: total ? valid / total : 0,
      issued, redeemed, redemptionRate: rewardEligible ? redeemed / rewardEligible : 0,
      averageDurationSeconds, blockedAttempts: blockedEvents.length,
      blockedIp: blockedEvents.filter(event => event.event_type === 'duplicate_ip').length,
      blockedDevice: blockedEvents.filter(event => event.event_type === 'duplicate_device').length
    },
    reasons, rewards, degrees, timeline, questions
  };
}

export function createSurveyServer(options = {}) {
  const root = options.root || ROOT;
  const dbPath = options.dbPath || process.env.SURVEY_DB_PATH || join(root, 'data', 'survey.sqlite');
  const adminPassword = options.adminPassword || process.env.ADMIN_PASSWORD || '';
  const adminSecret = options.adminSecret || process.env.ADMIN_SESSION_SECRET || randomBytes(32).toString('hex');
  const deviceSalt = options.deviceSalt || process.env.DEVICE_HASH_SALT || adminSecret;
  const trustProxy = options.trustProxy ?? process.env.TRUST_PROXY === '1';
  const testMode = options.testMode ?? process.env.TEST_MODE === '1';
  const commonTmallUrl = options.tmallUrl || process.env.TMALL_REDEEM_URL || DEFAULT_TMALL_REDEEM_URL;
  const prizeUrls = {
    m2: options.tmallM2Url || process.env.TMALL_M2_URL || commonTmallUrl,
    m10: options.tmallM10Url || process.env.TMALL_M10_URL || commonTmallUrl
  };
  const db = setupDatabase(dbPath);
  const rate = new Map();

  function limited(key, max, windowMs) {
    const now = Date.now();
    const entry = rate.get(key);
    if (!entry || entry.resetAt < now) { rate.set(key, { count: 1, resetAt: now + windowMs }); return false; }
    entry.count += 1;
    return entry.count > max;
  }

  const server = createServer(async (req, res) => {
    const url = new URL(req.url || '/', 'http://localhost');
    const ip = requestIp(req, trustProxy);
    const ipHash = hash(ip, deviceSalt);
    try {
      if (req.method === 'GET' && url.pathname === '/api/health') return json(res, 200, { ok: true });

      if (req.method === 'POST' && url.pathname === '/api/sessions') {
        if (limited(`session:${ip}`, testMode ? 120 : 30, 60_000)) return json(res, 429, { error: '请求过于频繁，请稍后再试' });
        const body = await readBody(req);
        const deviceId = String(body.deviceId || '').slice(0, 200);
        if (deviceId.length < 16) return json(res, 400, { error: '设备标识无效' });
        const id = randomBytes(24).toString('base64url');
        const deviceHash = hash(testMode ? `test:${id}:${deviceId}` : deviceId, deviceSalt);
        const sessionIpHash = hash(testMode ? `test:${id}:${ip}` : ip, deviceSalt);
        const existingDevice = testMode ? null : db.prepare("SELECT * FROM submissions WHERE device_hash = ? AND status = 'valid' ORDER BY id DESC LIMIT 1").get(deviceHash);
        if (existingDevice) {
          db.prepare('INSERT INTO anti_abuse_events(event_type, created_at, device_hash, ip_hash) VALUES(?,?,?,?)').run('duplicate_device', Date.now(), deviceHash, ipHash);
          return json(res, 200, {
          alreadyParticipated: true,
          matchedBy: 'device',
          rewardCode: existingDevice.reward_code,
          rewardStatus: existingDevice.reward_status,
          prizeName: existingDevice.prize_name,
          degreeLabel: existingDevice.degree_label,
          redeemUrl: existingDevice.redeem_url
          });
        }
        const existingIp = testMode ? null : db.prepare("SELECT 1 FROM submissions WHERE ip_hash = ? AND status = 'valid' LIMIT 1").get(ipHash);
        if (existingIp) {
          db.prepare('INSERT INTO anti_abuse_events(event_type, created_at, device_hash, ip_hash) VALUES(?,?,?,?)').run('duplicate_ip', Date.now(), deviceHash, ipHash);
          return json(res, 409, { error: '当前网络已经参与过本次活动，每个 IP 仅限一次', code: 'IP_ALREADY_PARTICIPATED' });
        }
        db.prepare('INSERT INTO survey_sessions(id, device_hash, started_at, ip_hash, user_agent) VALUES(?,?,?,?,?)')
          .run(id, deviceHash, Date.now(), sessionIpHash, String(req.headers['user-agent'] || '').slice(0, 500));
        return json(res, 201, { sessionId: id, minimumSeconds: FIVE_SECONDS_MS / 1000, testMode });
      }

      if (req.method === 'POST' && url.pathname === '/api/submissions') {
        if (limited(`submit:${ip}`, testMode ? 60 : 12, 60_000)) return json(res, 429, { error: '提交过于频繁，请稍后再试' });
        const body = await readBody(req);
        const deviceId = String(body.deviceId || '').slice(0, 200);
        const sessionId = String(body.sessionId || '').slice(0, 100);
        const session = db.prepare('SELECT * FROM survey_sessions WHERE id = ?').get(sessionId);
        const expectedDeviceHash = hash(testMode ? `test:${sessionId}:${deviceId}` : deviceId, deviceSalt);
        if (!session || deviceId.length < 16 || session.device_hash !== expectedDeviceHash) {
          return json(res, 400, { error: '答题会话无效，请刷新页面后重新填写' });
        }
        const existingSession = db.prepare('SELECT * FROM submissions WHERE session_id = ?').get(sessionId);
        if (existingSession) return json(res, 200, publicSubmission(existingSession, true));
        const existingDevice = testMode ? null : db.prepare("SELECT * FROM submissions WHERE device_hash = ? AND status = 'valid' ORDER BY id DESC LIMIT 1").get(session.device_hash);
        if (existingDevice) {
          db.prepare('INSERT INTO anti_abuse_events(event_type, created_at, device_hash, ip_hash) VALUES(?,?,?,?)').run('duplicate_device', Date.now(), session.device_hash, ipHash);
          return json(res, 200, publicSubmission(existingDevice, true));
        }
        const existingIp = testMode ? null : db.prepare("SELECT 1 FROM submissions WHERE ip_hash = ? AND status = 'valid' LIMIT 1").get(ipHash);
        if (existingIp) {
          db.prepare('INSERT INTO anti_abuse_events(event_type, created_at, device_hash, ip_hash) VALUES(?,?,?,?)').run('duplicate_ip', Date.now(), session.device_hash, ipHash);
          return json(res, 409, { error: '当前网络已经参与过本次活动，每个 IP 仅限一次', code: 'IP_ALREADY_PARTICIPATED' });
        }

        const answers = sanitizeAnswers(body.answers);
        const answerDetails = sanitizeAnswerDetails(body.answerDetails);
        const durationMs = Math.max(0, Date.now() - session.started_at);
        const reasons = antiCheatReasons(answers, durationMs);
        const prize = prizeForAnswers(answers, prizeUrls);
        if (!prize && !reasons.includes('INCOMPLETE')) reasons.push('INCOMPLETE');
        const status = reasons.length ? 'invalid' : 'valid';
        const code = status === 'valid' ? rewardCode(db, prize) : null;
        const result = db.prepare(`INSERT INTO submissions(
          session_id, device_hash, submitted_at, duration_ms, status, cheat_reasons,
          answers_json, answer_details_json, questionnaire_version, reward_code,
          prize_sku, prize_name, degree_label, redeem_url, reward_status, is_test, ip_hash, user_agent
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(
          sessionId, session.device_hash, Date.now(), durationMs, status, JSON.stringify(reasons),
          JSON.stringify(answers), JSON.stringify(answerDetails), String(body.questionnaireVersion || '2026-08-13').slice(0, 50),
          code, prize?.sku || null, prize?.name || null, prize?.degreeLabel || null, prize?.redeemUrl || null,
          code ? 'issued' : 'none', testMode ? 1 : 0, session.ip_hash, String(req.headers['user-agent'] || '').slice(0, 500)
        );
        const row = db.prepare('SELECT * FROM submissions WHERE id = ?').get(Number(result.lastInsertRowid));
        return json(res, 201, publicSubmission(row));
      }

      if (req.method === 'POST' && url.pathname === '/api/admin/login') {
        if (limited(`login:${ip}`, 8, 15 * 60_000)) return json(res, 429, { error: '登录尝试过多，请稍后再试' });
        if (!adminPassword) return json(res, 503, { error: '后台密码尚未配置' });
        const body = await readBody(req, 16 * 1024);
        if (!safeEqual(body.password || '', adminPassword)) return json(res, 401, { error: '密码错误' });
        const cookie = `${ADMIN_COOKIE}=${encodeURIComponent(signAdminToken(adminSecret))}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800`;
        return json(res, 200, { ok: true }, { 'set-cookie': cookie });
      }

      const isAdmin = validAdminToken(cookieMap(req)[ADMIN_COOKIE], adminSecret);
      if (url.pathname.startsWith('/api/admin/') && !isAdmin) return json(res, 401, { error: '请先登录后台' });

      if (req.method === 'POST' && url.pathname === '/api/admin/logout') {
        return json(res, 200, { ok: true }, { 'set-cookie': `${ADMIN_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0` });
      }

      if (req.method === 'GET' && url.pathname === '/api/admin/stats') {
        const totals = db.prepare(`SELECT COUNT(*) total,
          SUM(status='valid') valid, SUM(status='invalid') invalid,
          SUM(reward_status='issued') issued, SUM(reward_status='redeemed') redeemed
          FROM submissions`).get();
        const reasons = db.prepare("SELECT cheat_reasons reasons, COUNT(*) count FROM submissions WHERE status='invalid' GROUP BY cheat_reasons ORDER BY count DESC").all();
        return json(res, 200, { ...totals, reasons: reasons.map(r => ({ reasons: JSON.parse(r.reasons), count: r.count })) });
      }

      if (req.method === 'GET' && url.pathname === '/api/admin/analytics') {
        const status = ['valid', 'invalid'].includes(url.searchParams.get('status')) ? url.searchParams.get('status') : '';
        const dataScope = ['formal', 'test'].includes(url.searchParams.get('scope')) ? url.searchParams.get('scope') : 'all';
        const days = ['7', '30'].includes(url.searchParams.get('days')) ? Number(url.searchParams.get('days')) : null;
        const conditions = [];
        const params = [];
        if (status) { conditions.push('status = ?'); params.push(status); }
        if (dataScope !== 'all') { conditions.push('is_test = ?'); params.push(dataScope === 'test' ? 1 : 0); }
        const from = days ? Date.now() - days * 24 * 60 * 60 * 1000 : null;
        if (from) { conditions.push('submitted_at >= ?'); params.push(from); }
        const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
        const rows = db.prepare(`SELECT submitted_at, duration_ms, status, cheat_reasons, answer_details_json, prize_name, degree_label, reward_status, is_test FROM submissions ${where} ORDER BY submitted_at`).all(...params);
        const abuseWhere = from ? 'WHERE created_at >= ?' : '';
        const blockedEvents = dataScope === 'test' ? [] : db.prepare(`SELECT event_type, created_at FROM anti_abuse_events ${abuseWhere}`).all(...(from ? [from] : []));
        return json(res, 200, buildAnalytics(rows, blockedEvents, { status: status || 'all', days: days || 'all', dataScope }));
      }

      if (req.method === 'GET' && url.pathname === '/api/admin/submissions') {
        const status = ['valid', 'invalid'].includes(url.searchParams.get('status')) ? url.searchParams.get('status') : '';
        const dataScope = ['formal', 'test'].includes(url.searchParams.get('scope')) ? url.searchParams.get('scope') : 'all';
        const days = ['7', '30'].includes(url.searchParams.get('days')) ? Number(url.searchParams.get('days')) : null;
        const search = String(url.searchParams.get('search') || '').trim().slice(0, 100);
        const limit = Math.min(200, Math.max(1, Number(url.searchParams.get('limit')) || 50));
        const conditions = [];
        const params = [];
        if (status) { conditions.push('status = ?'); params.push(status); }
        if (dataScope !== 'all') { conditions.push('is_test = ?'); params.push(dataScope === 'test' ? 1 : 0); }
        if (days) { conditions.push('submitted_at >= ?'); params.push(Date.now() - days * 24 * 60 * 60 * 1000); }
        if (search) { conditions.push('(reward_code LIKE ? OR CAST(id AS TEXT) = ?)'); params.push(`%${search.toUpperCase()}%`, search); }
        const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
        const rows = db.prepare(`SELECT * FROM submissions ${where} ORDER BY submitted_at DESC LIMIT ?`).all(...params, limit);
        return json(res, 200, rows.map(row => ({
          id: row.id, submittedAt: row.submitted_at, durationMs: row.duration_ms, status: row.status,
          reasons: JSON.parse(row.cheat_reasons), rewardCode: row.reward_code, rewardStatus: row.reward_status,
          prizeSku: row.prize_sku, prizeName: row.prize_name, degreeLabel: row.degree_label, redeemUrl: row.redeem_url,
          redeemedAt: row.redeemed_at, redeemedBy: row.redeemed_by, staffNote: row.staff_note,
          isTest: Boolean(row.is_test),
          answers: JSON.parse(row.answers_json), answerDetails: JSON.parse(row.answer_details_json)
        })));
      }

      const redeemMatch = url.pathname.match(/^\/api\/admin\/rewards\/([^/]+)\/redeem$/);
      if (req.method === 'POST' && redeemMatch) {
        const code = decodeURIComponent(redeemMatch[1]).trim().toUpperCase();
        const body = await readBody(req, 32 * 1024);
        const row = db.prepare('SELECT * FROM submissions WHERE reward_code = ?').get(code);
        if (!row) return json(res, 404, { error: '兑换码不存在' });
        if (row.reward_status === 'redeemed') return json(res, 409, { error: '该兑换码已经核销', redeemedAt: row.redeemed_at, redeemedBy: row.redeemed_by });
        if (row.status !== 'valid' || row.reward_status !== 'issued') return json(res, 409, { error: '该兑换码不可用' });
        const now = Date.now();
        db.prepare("UPDATE submissions SET reward_status='redeemed', redeemed_at=?, redeemed_by=?, staff_note=? WHERE id=? AND reward_status='issued'")
          .run(now, String(body.staffName || '工作人员').trim().slice(0, 100), String(body.note || '').trim().slice(0, 500), row.id);
        return json(res, 200, { ok: true, code, redeemedAt: now });
      }

      if (req.method === 'GET' && url.pathname === '/api/admin/export.csv') {
        const status = ['valid', 'invalid'].includes(url.searchParams.get('status')) ? url.searchParams.get('status') : '';
        const dataScope = ['formal', 'test'].includes(url.searchParams.get('scope')) ? url.searchParams.get('scope') : 'all';
        const days = ['7', '30'].includes(url.searchParams.get('days')) ? Number(url.searchParams.get('days')) : null;
        const conditions = [];
        const params = [];
        if (status) { conditions.push('status = ?'); params.push(status); }
        if (dataScope !== 'all') { conditions.push('is_test = ?'); params.push(dataScope === 'test' ? 1 : 0); }
        if (days) { conditions.push('submitted_at >= ?'); params.push(Date.now() - days * 24 * 60 * 60 * 1000); }
        const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
        const rows = db.prepare(`SELECT * FROM submissions ${where} ORDER BY submitted_at DESC`).all(...params);
        const questionIds = [...new Set(rows.flatMap(row => JSON.parse(row.answer_details_json).map(item => item.id)))];
        const header = ['提交ID','数据类型','提交时间','答题秒数','答卷状态','异常原因','奖品规格','度数','兑换码','兑换状态','核销时间','核销人','核销备注', ...questionIds];
        const lines = [header.map(csvCell).join(',')];
        for (const row of rows) {
          const details = Object.fromEntries(JSON.parse(row.answer_details_json).map(item => [item.id, [...item.answerLabels, item.otherText].filter(Boolean).join(' | ')]));
          lines.push([
            row.id, row.is_test ? '测试数据' : '正式数据', new Date(row.submitted_at).toISOString(), (row.duration_ms / 1000).toFixed(1), row.status,
            JSON.parse(row.cheat_reasons).join('|'), row.prize_name, row.degree_label, row.reward_code, row.reward_status,
            row.redeemed_at ? new Date(row.redeemed_at).toISOString() : '', row.redeemed_by, row.staff_note,
            ...questionIds.map(id => details[id] || '')
          ].map(csvCell).join(','));
        }
        const content = '\uFEFF' + lines.join('\r\n');
        res.writeHead(200, {
          'content-type': 'text/csv; charset=utf-8',
          'content-disposition': `attachment; filename="survey-${new Date().toISOString().slice(0, 10)}.csv"`,
          'cache-control': 'no-store'
        });
        return res.end(content);
      }

      if (!['GET', 'HEAD'].includes(req.method || '')) return json(res, 404, { error: '接口不存在' });
      let pathname = decodeURIComponent(url.pathname);
      if (pathname === '/') pathname = '/index.html';
      if (pathname === '/admin') pathname = '/admin.html';
      const file = resolve(root, `.${normalize(pathname)}`);
      const resolvedRoot = resolve(root);
      if (!(file === resolvedRoot || file.startsWith(`${resolvedRoot}${sep}`)) || !existsSync(file)) return json(res, 404, { error: '页面不存在' });
      const fileStat = statSync(file);
      if (!fileStat.isFile()) return json(res, 404, { error: '页面不存在' });
      const noCache = pathname.endsWith('.html') || pathname === '/survey-submit.js';
      const versionedAsset = url.searchParams.has('v');
      res.writeHead(200, {
        'content-type': MIME[extname(file).toLowerCase()] || 'application/octet-stream',
        'cache-control': noCache ? 'no-cache' : versionedAsset ? 'public, max-age=31536000, immutable' : 'public, max-age=604800',
        'content-length': fileStat.size,
        'last-modified': fileStat.mtime.toUTCString(),
        'x-content-type-options': 'nosniff',
        'referrer-policy': 'same-origin'
      });
      if (req.method === 'HEAD') return res.end();
      return createReadStream(file).pipe(res);
    } catch (error) {
      console.error(error);
      if (!res.headersSent) json(res, error.statusCode || 500, { error: error.statusCode ? error.message : '服务器内部错误' });
      else res.end();
    }
  });

  server.on('close', () => db.close());
  return { server, db };
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const port = Number(process.env.PORT || 3000);
  const host = process.env.HOST || '127.0.0.1';
  const { server } = createSurveyServer();
  server.listen(port, host, () => {
    console.log(`问卷地址：http://${host}:${port}`);
    console.log(`管理后台：http://${host}:${port}/admin`);
    if (!process.env.ADMIN_PASSWORD) console.warn('警告：未配置 ADMIN_PASSWORD，后台登录已禁用。');
  });
}
