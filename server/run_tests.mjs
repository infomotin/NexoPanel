import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';
import crypto from 'node:crypto';

const srv = spawn('node', ['server/index.js'], {
  stdio: 'inherit',
  env: {
    ...process.env,
    PORT: '3001',
    // The server refuses to start without an explicit signing secret.
    JWT_SECRET: process.env.JWT_SECRET || crypto.randomBytes(48).toString('base64url'),
    // Test fixtures rely on the opt-in demo accounts.
    NEXOPANEL_SEED_DEMO_ACCOUNTS: '1',
  },
});

srv.on('error', (err) => {
  console.error('Failed to spawn server:', err);
  process.exit(1);
});

await sleep(1500);

const testProc = spawn('node', ['--test', 'server/test_security.mjs'], {
  stdio: 'inherit',
  env: { ...process.env, TEST_BASE_URL: 'http://127.0.0.1:3001/api' },
});

testProc.on('exit', (code) => {
  srv.kill('SIGTERM');
  process.exit(code || 0);
});
