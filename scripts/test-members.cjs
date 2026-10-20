// Contract tests for the portal. These do not replace VPS authorization tests.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const source = readFileSync(require('node:path').join(__dirname, '../js/membres.js'), 'utf8');

async function portal(status, marker, fails = false, grants = [{id:'g1crm',allowed:true,enabled:true}]) {
  const elements = new Map();
  const events = {};
  function element(tag = 'div') {
    return { tag, hidden: true, value: '', children: [], dataset: {}, style: { setProperty() {} },
      setAttribute() {}, addEventListener(event, fn) { this[event] = fn; },
      append(...children) { this.children.push(...children); },
      replaceChildren() { this.children = []; } };
  }
  const document = {
    hidden: false,
    getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
    createElement: element, addEventListener(event, fn) { events[event] = fn; },
  };
  vm.runInNewContext(source, { document, window: { addEventListener(event, fn) { events[event] = fn; } },
    AbortSignal, fetch: async (url, options) => {
      assert.equal(url, '/api/member-session');
      assert.equal(options.cache, 'no-store');
      assert.equal(options.redirect, 'error');
      if (fails) throw new Error('Network unavailable');
      return { status, headers: { get: () => marker }, json: async () => ({user:{name:'Marie',is_admin:false},csrf:'test-csrf',applications:grants.map(app => ({name:app.id,description:'Application',...app}))}) };
    } });
  await events.pageshow();
  return elements;
}
function links(elements) {
  return elements.get('applications').children.flatMap(card => card.children.filter(child => child.tag === 'a'));
}
test('401 offers sign-in without application links', async () => {
  const e = await portal(401); assert.equal(e.get('login').hidden, false); assert.equal(links(e).length, 0);
});
test('authenticated response exposes only individually assigned applications', async () => {
  const e = await portal(200, 'authenticated');
  assert.deepEqual(links(e).map(link => link.href), ['/auth/apps/g1crm/open/']);
  assert.equal(e.get('account').hidden, false);
});

test('old portal URLs remain compatible and other destinations are rejected', async () => {
  for (const [url, expected] of [
    ['https://g1crm.devantiq.com', 'https://g1crm.devantiq.com/'],
    ['https://g1crm.devantiq.com/', 'https://g1crm.devantiq.com/'],
    ['https://evil.example/', '/auth/apps/g1crm/open/'],
  ]) {
    const e = await portal(200, 'authenticated', false, [{id:'g1crm',allowed:true,enabled:true,url}]);
    assert.equal(links(e)[0].href, expected);
  }
});

test('landing image falls back once when a future application has no capture', async () => {
  const e = await portal(200, 'authenticated');
  const image = e.get('applications').children[0].children[0].children[0];
  assert.equal(image.src, 'img/members/g1crm-landing.png');
  image.error();
  assert.equal(image.src, 'img/members/g1crm-scene.svg');
  image.error();
  assert.equal(image.hidden, true);
});

test('unassigned and inactive applications remain locked', async () => {
  const e = await portal(200, 'authenticated', false, [{id:'g1crm',allowed:true,enabled:false},{id:'n8n',allowed:false,enabled:true}]);
  assert.equal(links(e).length, 0);
});
test('static 200 fallback never grants access', async () => {
  const e = await portal(200, null); assert.equal(links(e).length, 0); assert.equal(e.get('retry').hidden, false);
});
test('403 does not unlock applications even with a misleading marker', async () => {
  const e = await portal(403, 'authenticated'); assert.equal(links(e).length, 0); assert.equal(e.get('account').hidden, false);
});
test('outage and missing endpoint fail closed', async () => {
  for (const [status, fail] of [[404, false], [503, false], [200, true]]) {
    const e = await portal(status, null, fail); assert.equal(links(e).length, 0); assert.equal(e.get('retry').hidden, false);
  }
});
test('search filters and reports no results', async () => {
  const e = await portal(401); const search = e.get('search');
  search.value = 'ZABBIX'; search.input(); assert.equal(e.get('applications').children.length, 1);
  search.value = 'inexistant'; search.input(); assert.equal(e.get('empty').hidden, false);
});

test('future applications are displayed without allowing injected destinations', async () => {
  const e = await portal(200, 'authenticated', false, [
    {id:'future-app',name:'Future App',description:'Nouvelle application',allowed:true,enabled:true,url:'https://evil.test'},
    {id:'../evil',allowed:true,enabled:true}
  ]);
  assert.deepEqual(links(e).map(link => link.href), ['/auth/apps/future-app/open/']);
  assert.equal(e.get('applications').children.length, 1);
});
