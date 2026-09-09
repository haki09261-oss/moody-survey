const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('IP column renders safely and exports the same location next to the correct code', async () => {
  const html = fs.readFileSync(path.join(__dirname, '../web/admin/index.html'), 'utf8');
  const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const nodes = new Map();
  const document = {
    querySelector(selector) {
      if (!nodes.has(selector)) nodes.set(selector, {
        value: selector === '#days' || selector === '#scope' ? 'all' : '',
        textContent: '', innerHTML: '', classList: { add() {}, remove() {}, toggle() {} },
      });
      return nodes.get(selector);
    },
    querySelectorAll() { return []; },
    createElement() { return { click() {} }; },
  };
  const row = {
    id: 12, ip: '113.118.113.77', status: 'new', reward_status: 'issued',
    display_code: 'WJ-GEO00102-525', participant_id: 'mp-anonymous',
    ip_location: { label: '中国 · 广东省 · 深圳市', country: '中国', province: '广东省', city: '深圳市',
      isp: '电信', note: '网络出口位置，仅供辅助核对', source: 'ip2region 离线库' },
  };
  let exported;
  const context = vm.createContext({ document, console, URLSearchParams, Blob, AbortController,
    URL: { createObjectURL(blob) { exported = blob; return 'blob:test'; }, revokeObjectURL() {} },
    setTimeout() {}, clearTimeout() {}, alert(message) { throw Error(message); }, sample: row,
    location: { reload() {} },
    fetch: async () => ({ ok: true, json: async () => ({ items: [row] }) }),
  });
  vm.runInContext(script, context);
  vm.runInContext("state.dashboardStatus='ready';state.total=1;state.auth='test';renderRows([sample]);", context);
  const rendered = nodes.get('#rows').innerHTML;
  assert.ok(rendered.includes(row.display_code));
  assert.ok(rendered.includes(row.ip_location.label));
  assert.ok(rendered.includes(row.ip));
  await vm.runInContext('exportCsv()', context);
  const csv = await exported.text();
  const lines = csv.split('\r\n').map(line => line.replace(/^\ufeff/, '').slice(1, -1).split('","'));
  assert.equal(lines[0].length, lines[1].length);
  for (const [header, expected] of Object.entries({ 提交IP: row.ip, 城市: '深圳市', 兑换码: row.display_code })) {
    assert.equal(lines[1][lines[0].indexOf(header)], expected);
  }
  context.sample = { ...row, ip: '<img src=x onerror=alert(1)>', ip_location: null };
  vm.runInContext('renderRows([sample])', context);
  assert.ok(nodes.get('#rows').innerHTML.includes('归属地暂不可用'));
  assert.ok(!nodes.get('#rows').innerHTML.includes('<img'));
  assert.equal(vm.runInContext("csvCell('=1+1')", context), '"\'=1+1"');
});
