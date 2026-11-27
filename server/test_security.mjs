import test from 'node:test';
import assert from 'node:assert/strict';

const BASE = process.env.TEST_BASE_URL || 'http://127.0.0.1:3001/api';

let token = '';

test('Security: rejects unauthenticated requests and bad credentials', async () => {
  const unauth = await fetch(`${BASE}/websites`);
  assert.equal(unauth.status, 401);

  const badLogin = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'aapanel', password: 'wrong-password' }),
  });
  assert.equal(badLogin.status, 401);

  const goodLogin = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'aapanel', password: 'aapanel' }),
  });
  assert.equal(goodLogin.status, 200);
  const data = await goodLogin.json();
  assert.ok(data.token);
  token = data.token;
});

test('Security: blocks path traversal in File Manager', async () => {
  const headers = { Authorization: `Bearer ${token}` };
  const listTraversal = await fetch(`${BASE}/files/list?path=../../etc`, { headers });
  assert.equal(listTraversal.status, 403);

  const readTraversal = await fetch(`${BASE}/files/read?path=../../../Windows/System32/drivers/etc/hosts`, { headers });
  assert.equal(readTraversal.status, 403);

  const writeTraversal = await fetch(`${BASE}/files/write`, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: '../../pwned.txt', content: 'x' }),
  });
  assert.equal(writeTraversal.status, 403);
});

test('Operations: Website, Database, File, Cron, Firewall, and App Store flows', async () => {
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  // 1. Website CRUD
  const siteRes = await fetch(`${BASE}/websites`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ domain: `sec-test-${Date.now()}.local`, project_type: 'php', php_version: '8.3', ssl_enabled: true }),
  });
  assert.equal(siteRes.status, 201);
  const site = await siteRes.json();
  const siteDel = await fetch(`${BASE}/websites/${site.id}`, { method: 'DELETE', headers });
  assert.equal(siteDel.status, 200);

  // 2. Database CRUD + Password Rotate + Backup/Restore
  const dbRes = await fetch(`${BASE}/databases`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ engine: 'mysql', db_name: `db_${Date.now()}`, username: 'u_test', password: 'InitialPass123!' }),
  });
  assert.equal(dbRes.status, 201);
  const dbRow = await dbRes.json();
  const pwRes = await fetch(`${BASE}/databases/${dbRow.id}/password`, {
    method: 'PUT',
    headers,
    body: JSON.stringify({ password: 'RotatedPass456!' }),
  });
  assert.equal(pwRes.status, 200);
  const bkpRes = await fetch(`${BASE}/databases/${dbRow.id}/backup`, { method: 'POST', headers });
  assert.equal(bkpRes.status, 200);
  await fetch(`${BASE}/databases/${dbRow.id}`, { method: 'DELETE', headers });

  // 3. File Manager Write -> Read -> Chmod -> Rename -> Delete
  const fName = `sec_${Date.now()}.txt`;
  const fRenamed = `sec_renamed_${Date.now()}.txt`;
  assert.equal((await fetch(`${BASE}/files/write`, { method: 'POST', headers, body: JSON.stringify({ path: fName, content: 'hello' }) })).status, 200);
  assert.equal((await fetch(`${BASE}/files/chmod`, { method: 'POST', headers, body: JSON.stringify({ path: fName, mode: '0644' }) })).status, 200);
  assert.equal((await fetch(`${BASE}/files/rename`, { method: 'POST', headers, body: JSON.stringify({ source: fName, destination: fRenamed }) })).status, 200);
  assert.equal((await fetch(`${BASE}/files?path=${encodeURIComponent(fRenamed)}`, { method: 'DELETE', headers })).status, 200);

  // 4. Cron + Firewall + Security Scan + App Store
  const cronRes = await fetch(`${BASE}/cron`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ name: 'Test Cron', task_type: 'shell', schedule: '*/5 * * * *', script_content: 'echo ok' }),
  });
  assert.equal(cronRes.status, 201);
  const cronJob = await cronRes.json();
  assert.equal((await fetch(`${BASE}/cron/${cronJob.id}/run`, { method: 'POST', headers })).status, 200);
  await fetch(`${BASE}/cron/${cronJob.id}`, { method: 'DELETE', headers });

  const fwRes = await fetch(`${BASE}/security/firewall/rules`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ protocol: 'tcp', port: '9000', strategy: 'allow', direction: 'inbound' }),
  });
  assert.equal(fwRes.status, 201);
  const fwRule = await fwRes.json();
  await fetch(`${BASE}/security/firewall/rules/${fwRule.id}`, { method: 'DELETE', headers });

  const scanRes = await fetch(`${BASE}/security/scan`, { method: 'POST', headers });
  assert.equal(scanRes.status, 200);

  const apps = await (await fetch(`${BASE}/apps`, { headers })).json();
  assert.ok(apps.length > 0);
});
