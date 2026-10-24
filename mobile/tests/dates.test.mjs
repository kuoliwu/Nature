import assert from 'node:assert/strict';
import { test } from 'node:test';

import { slotsPerDay } from '../src/lib/dates.ts';

test('每天時段數扣除屏蔽區段', () => {
  assert.equal(slotsPerDay('09:00', '17:00'), 16);
  assert.equal(slotsPerDay('09:00', '17:00', [{ start: '12:00', end: '13:00' }]), 14);
  assert.equal(slotsPerDay('09:00', '17:00', [{ start: '12:00', end: '13:00' }, { start: '15:15', end: '15:45' }]), 12);
  assert.equal(slotsPerDay('09:00', '09:20'), 0);
});
