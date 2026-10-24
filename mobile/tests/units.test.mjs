import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseUnitList } from '../src/lib/units.ts';

test('一行一戶或逗號分隔都能解析', () => {
  assert.deepEqual(parseUnitList('A-1F-1\nA-1F-2\n\n A-2F-1 '), ['A-1F-1', 'A-1F-2', 'A-2F-1']);
  assert.deepEqual(parseUnitList('A-1F-1, A-1F-2，A-1F-3、A-1F-4'), ['A-1F-1', 'A-1F-2', 'A-1F-3', 'A-1F-4']);
  assert.deepEqual(parseUnitList('A1\r\nA2\tA3;A3'), ['A1', 'A2', 'A3']);
});

import { generateUnits } from '../src/lib/units.ts';

const gen = (o) => generateUnits({ format: 'dash', ...o });

test('棟別 × 樓層排列組合', () => {
  const r = gen({ letterFrom: 'a', letterTo: 'B', floorFrom: 2, floorTo: 3 });
  assert.deepEqual(r.units.map((u) => u.unit_no), ['A-2F', 'A-3F', 'B-2F', 'B-3F']);
  assert.deepEqual(r.units[2], { unit_no: 'B-2F', building: 'B', floor: '2F' });
});

test('加上每層戶號與不同格式', () => {
  const r = gen({ letterFrom: 'A', letterTo: 'A', floorFrom: 5, floorTo: 5, perFloorFrom: 1, perFloorTo: 3 });
  assert.deepEqual(r.units.map((u) => u.unit_no), ['A-5F-1', 'A-5F-2', 'A-5F-3']);
  const c = generateUnits({ letterFrom: 'C', letterTo: '', floorFrom: 12, floorTo: 12, perFloorFrom: 2, perFloorTo: 2, format: 'chinese' });
  assert.deepEqual(c.units.map((u) => u.unit_no), ['C棟12樓之2']);
  const k = generateUnits({ letterFrom: 'B', letterTo: 'B', floorFrom: 3, floorTo: 3, format: 'compact' });
  assert.deepEqual(k.units.map((u) => u.unit_no), ['B3']);
});

test('輸入錯誤時回傳說明', () => {
  assert.match(gen({ letterFrom: 'AB', letterTo: 'C', floorFrom: 1, floorTo: 2 }).error, /單一英文字母/);
  assert.match(gen({ letterFrom: 'C', letterTo: 'A', floorFrom: 1, floorTo: 2 }).error, /結束字母/);
  assert.match(gen({ letterFrom: 'A', letterTo: 'A', floorFrom: 5, floorTo: 2 }).error, /結束樓層/);
  assert.match(gen({ letterFrom: 'A', letterTo: 'A', floorFrom: 0, floorTo: 2 }).error, /1～99/);
  assert.match(gen({ letterFrom: 'A', letterTo: 'Z', floorFrom: 1, floorTo: 99, perFloorFrom: 1, perFloorTo: 2 }).error, /最多/);
});
