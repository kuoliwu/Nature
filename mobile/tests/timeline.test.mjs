import assert from 'node:assert/strict';
import { test } from 'node:test';

import { stepRange, stepSubText, timelineProgress } from '../src/lib/timeline.ts';

const step = (status, extra = {}) => ({ key: 'k', label: 'x', status, done: 0, total: 10, date_from: null, date_to: null, note: '', ...extra });
const tl = (statuses, current, extra = {}) => ({
  project: { id: 1, name: 'p', address: '', unit_count: 10 },
  current,
  steps: statuses.map((s, i) => step(s, i === current ? extra : {})),
});

test('進度條填到目前步驟加上完成比例', () => {
  assert.equal(timelineProgress(tl(['done', 'todo', 'todo', 'todo', 'todo', 'todo', 'todo'], 1)), 0);
  assert.equal(timelineProgress(tl(['done', 'done', 'active', 'todo', 'todo', 'todo', 'todo'], 2, { done: 5 })), 1.5 / 6);
  assert.equal(timelineProgress(tl(['done', 'done', 'todo', 'todo', 'todo', 'todo', 'todo'], 2)), 1 / 6);
  assert.equal(timelineProgress(tl(Array(7).fill('done'), 6)), 1);
  assert.equal(timelineProgress(tl(['done', 'active', 'todo', 'todo', 'todo', 'todo', 'todo'], 1, { done: 3, total: 0 })), 0);
});

test('節點第二行與日期區間', () => {
  assert.equal(stepSubText(step('active', { done: 3 })), '3/10');
  assert.equal(stepSubText(step('done', { date_from: '2026-11-03', date_to: '2026-11-20' })), '11/20');
  assert.equal(stepSubText(step('todo', { date_from: '2026-12-01' })), '12/1');
  assert.equal(stepSubText(step('todo')), '');
  assert.equal(stepRange(step('todo', { date_from: '2026-11-03', date_to: '2026-11-20' })), '11/3–11/20');
  assert.equal(stepRange(step('todo', { date_from: '2026-11-03', date_to: '2026-11-03' })), '11/3');
});
