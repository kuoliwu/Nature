// 後端錯誤訊息：後端還是舊版（找不到新 API）時要提示重新啟動
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { api, configureApi } from '../src/lib/api.ts';

function fakeFetch(status, body) {
  globalThis.fetch = async () => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

configureApi({ baseUrl: 'http://backend.test', token: 't' });

test('找不到 API（後端舊版）→ 提示重新啟動後端', async () => {
  fakeFetch(404, { detail: 'Not Found' });
  await assert.rejects(api.projectBackupLink(1), /後端版本較舊.*重新啟動後端/);
  fakeFetch(405, { detail: 'Method Not Allowed' });
  await assert.rejects(api.saveProjectOrder([1]), /後端版本較舊/);
});

test('我們自己的 404（中文訊息）照原文顯示', async () => {
  fakeFetch(404, { detail: '找不到建案' });
  await assert.rejects(api.projectBackupLink(999), (e) => e.message === '找不到建案' && e.status === 404);
});
