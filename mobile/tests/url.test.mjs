// node --test tests/url.test.mjs  （Node 22.18+ 可直接載入 .ts）
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { normalizeBaseUrl } from '../src/lib/url.ts';

test('只填 IP 時補上 http 與預設 port 8000', () => {
  assert.equal(normalizeBaseUrl('192.168.68.109'), 'http://192.168.68.109:8000');
  assert.equal(normalizeBaseUrl('  192.168.68.109:8000/ '), 'http://192.168.68.109:8000');
});

test('有寫協定時保留原樣、不補 port', () => {
  assert.equal(normalizeBaseUrl('http://100.64.1.2:8000/'), 'http://100.64.1.2:8000');
  assert.equal(normalizeBaseUrl('HTTPS://laptop.tail1234.ts.net'), 'https://laptop.tail1234.ts.net');
});

test('格式錯誤回傳 null', () => {
  for (const bad of ['', '   ', 'ftp://1.2.3.4', '1.2.3.4:99999', 'http://a b', '1.2.3.4/path']) {
    assert.equal(normalizeBaseUrl(bad), null, bad);
  }
});
