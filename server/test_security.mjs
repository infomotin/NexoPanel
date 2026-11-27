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

test('FTP Module: full aaPanel parity & security validation', async () => {
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  // Security validations: bad username, critical path, path traversal, invalid port & IP
  assert.equal((await fetch(`${BASE}/ftp`, { method: 'POST', headers, body: JSON.stringify({ username: 'bad user!', password: 'FtpPass123!', document_root: '/www/wwwroot/x' }) })).status, 400);
  assert.equal((await fetch(`${BASE}/ftp`, { method: 'POST', headers, body: JSON.stringify({ username: 'valid_u1', password: 'FtpPass123!', document_root: '/etc' }) })).status, 403);
  assert.equal((await fetch(`${BASE}/ftp`, { method: 'POST', headers, body: JSON.stringify({ username: 'valid_u2', password: 'FtpPass123!', document_root: '/www/wwwroot/../../etc' }) })).status, 403);
  assert.equal((await fetch(`${BASE}/ftp/port`, { method: 'PUT', headers, body: JSON.stringify({ port: 70000 }) })).status, 400);
  assert.equal((await fetch(`${BASE}/ftp/whitelist`, { method: 'POST', headers, body: JSON.stringify({ ip: 'not-an-ip' }) })).status, 400);

  // Create FTP user -> Overview -> Password -> Set Path -> Note -> Quota -> Logs -> Scan -> Whitelist -> Batch Delete
  const uname = `ftp_test_${Date.now()}`.slice(0, 24);
  const created = await fetch(`${BASE}/ftp`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ username: uname, password: 'StrongFtpPass99!', document_root: `/www/wwwroot/${uname}`, quota_mb: 512, note: 'Test FTP' }),
  });
  assert.equal(created.status, 201);
  const ftpRow = await created.json();

  const ov = await (await fetch(`${BASE}/ftp/overview`, { headers })).json();
  assert.ok(Array.isArray(ov.items));

  assert.equal((await fetch(`${BASE}/ftp/${ftpRow.id}/password`, { method: 'PUT', headers, body: JSON.stringify({ password: 'RotatedFtp99!' }) })).status, 200);
  assert.equal((await fetch(`${BASE}/ftp/${ftpRow.id}/home`, { method: 'PUT', headers, body: JSON.stringify({ document_root: `/www/wwwroot/${uname}_v2`, migrate: true }) })).status, 200);
  assert.equal((await fetch(`${BASE}/ftp/${ftpRow.id}/note`, { method: 'PUT', headers, body: JSON.stringify({ note: 'Migrated' }) })).status, 200);
  assert.equal((await fetch(`${BASE}/ftp/${ftpRow.id}/quota`, { method: 'PUT', headers, body: JSON.stringify({ quota_mb: 1024 }) })).status, 200);
  assert.equal((await fetch(`${BASE}/ftp/${ftpRow.id}/logs/login`, { headers })).status, 200);
  assert.equal((await fetch(`${BASE}/ftp/${ftpRow.id}/logs/action`, { headers })).status, 200);
  assert.equal((await fetch(`${BASE}/ftp/security`, { method: 'PUT', headers, body: JSON.stringify({ no_anonymous: true, forbid_root: true }) })).status, 200);

  const scanRes = await (await fetch(`${BASE}/ftp/log-analysis/scan`, { method: 'POST', headers, body: JSON.stringify({ types: ['login_error', 'upload_shell', 'area', 'anonymous'], day: 30 }) })).json();
  assert.ok(scanRes.total >= 1);

  assert.equal((await fetch(`${BASE}/ftp/whitelist`, { method: 'POST', headers, body: JSON.stringify({ ip: '198.51.100.24' }) })).status, 200);
  assert.equal((await fetch(`${BASE}/ftp/whitelist/198.51.100.24`, { method: 'DELETE', headers })).status, 200);

  const batchDel = await (await fetch(`${BASE}/ftp/batch-delete`, { method: 'POST', headers, body: JSON.stringify({ ids: [ftpRow.id] }) })).json();
  assert.equal(batchDel.results[0].ok, true);
});

test('Packages & Runtimes: Curated Software Stacks, PHP Detection & Control', async () => {
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  // 1. Curated package catalog
  const catalogRes = await fetch(`${BASE}/system/packages/catalog`, { headers });
  assert.equal(catalogRes.status, 200);
  const catalog = await catalogRes.json();
  assert.ok(catalog.length > 5);
  const slugs = catalog.map((p) => p.slug);
  assert.ok(slugs.includes('nginx'));
  assert.ok(slugs.includes('php8.4'));
  assert.ok(slugs.includes('mariadb'));
  assert.ok(slugs.includes('pure-ftpd'));

  // 2. Filter by category
  const phpCatalog = await (await fetch(`${BASE}/system/packages/catalog?category=PHP`, { headers })).json();
  assert.ok(phpCatalog.every((p) => p.category.toLowerCase() === 'php'));

  // 3. PHP runtime detection
  const runtimes = await (await fetch(`${BASE}/system/runtimes/php`, { headers })).json();
  assert.ok(runtimes.some((r) => r.version === '8.4'));
  assert.ok(runtimes.some((r) => r.version === '8.3'));

  // 4. Curated service control
  const controlRes = await fetch(`${BASE}/system/packages/curated/nginx/control`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ action: 'restart' }),
  });
  assert.equal(controlRes.status, 200);
  assert.equal((await controlRes.json()).ok, true);

  // 5. Curated install & uninstall streaming endpoints
  const inst = await fetch(`${BASE}/system/packages/curated/nginx/install`, { method: 'POST', headers });
  assert.equal(inst.status, 200);
  assert.ok(inst.headers.get('content-type').includes('text/event-stream'));

  const uninst = await fetch(`${BASE}/system/packages/curated/nginx/uninstall`, { method: 'POST', headers });
  assert.equal(uninst.status, 200);
  assert.ok(uninst.headers.get('content-type').includes('text/event-stream'));

  const update = await fetch(`${BASE}/system/packages/update-cache`, { method: 'POST', headers });
  assert.equal(update.status, 200);
  assert.ok(update.headers.get('content-type').includes('text/event-stream'));
});
