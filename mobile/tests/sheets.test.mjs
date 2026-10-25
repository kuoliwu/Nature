import assert from 'node:assert/strict';
import { test } from 'node:test';

import { sheetQuery } from '../src/lib/api.ts';

test('匯出匯入的查詢字串略過空值', () => {
  assert.equal(sheetQuery({}), '');
  assert.equal(sheetQuery({ batch_id: 3, format: 'xlsx' }), '?batch_id=3&format=xlsx');
  assert.equal(sheetQuery({ project_id: 1, service: 'health_check', dry_run: true }), '?project_id=1&service=health_check&dry_run=true');
  assert.equal(sheetQuery({ project_id: undefined, dry_run: false }), '?dry_run=false');
});
