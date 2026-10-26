// node --test tests/url.test.mjs  （Node 22.18+ 可直接載入 .ts）
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { hostWhenServedByBackend, normalizeBaseUrl, suggestHostForWeb, suggestHostFromDevServer } from '../src/lib/url.ts';

test('只填 IP 時補上 http 與預設 port 8000', () => {
  assert.equal(normalizeBaseUrl('192.168.68.109'), 'http://192.168.68.109:8000');
  assert.equal(normalizeBaseUrl('  192.168.68.109:8000/ '), 'http://192.168.68.109:8000');
});

test('有寫協定時保留原樣、不補 port', () => {
  assert.equal(normalizeBaseUrl('http://100.64.1.2:8000/'), 'http://100.64.1.2:8000');
  assert.equal(normalizeBaseUrl('HTTPS://laptop.tail1234.ts.net'), 'https://laptop.tail1234.ts.net');
});

test('手機輸入常見狀況會自動修正', () => {
  assert.equal(normalizeBaseUrl('192．168．68．109：8000'), 'http://192.168.68.109:8000'); // 全形
  assert.equal(normalizeBaseUrl('192。168。68。109:8000'), 'http://192.168.68.109:8000'); // 中文句號
  assert.equal(normalizeBaseUrl('192.168.68.109 : 8000'), 'http://192.168.68.109:8000'); // 空格
  assert.equal(normalizeBaseUrl('http://192.168.68.109:8000/docs'), 'http://192.168.68.109:8000'); // 多了路徑
  assert.equal(normalizeBaseUrl('Http://192.168.68.109:8000/'), 'http://192.168.68.109:8000'); // 自動大寫
});

test('格式錯誤回傳 null', () => {
  for (const bad of ['', '   ', 'ftp://1.2.3.4', '1.2.3.4:99999', '1.2.3.4:', 'http://', '.1.2.3', 'a_b.c']) {
    assert.equal(normalizeBaseUrl(bad), null, bad);
  }
});

test('從開發伺服器位址建議後端位址', () => {
  assert.equal(suggestHostFromDevServer('192.168.68.109:8081'), '192.168.68.109:8000');
  assert.equal(suggestHostFromDevServer(undefined), null);
  assert.equal(suggestHostFromDevServer('abc.exp.direct'), null);
});

test('網頁版建議用網頁本身的主機', () => {
  assert.equal(suggestHostForWeb('localhost'), 'localhost:8000');
  assert.equal(suggestHostForWeb(''), null);
});

test('由後端提供的電腦版自動使用網頁本身的主機', () => {
  assert.equal(hostWhenServedByBackend({ host: 'localhost:8000', pathname: '/app/inspections' }), 'localhost:8000');
  assert.equal(hostWhenServedByBackend({ host: 'localhost:8081', pathname: '/inspections' }), null);
  // 對外 https（Tailscale Funnel）要保留協定與 port
  const served = hostWhenServedByBackend({ protocol: 'https:', host: 'laptop.example.ts.net:8443', pathname: '/app/' });
  assert.equal(served, 'https://laptop.example.ts.net:8443');
  assert.equal(normalizeBaseUrl(served), 'https://laptop.example.ts.net:8443');
});
