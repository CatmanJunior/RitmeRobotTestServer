import assert from 'node:assert/strict';
import { test } from 'node:test';
import { classifyExport } from '../scripts/validate-godot-export.mjs';

const complete = '[ DONE ] savepack\n';
const crash = 'CrashHandlerException: Program crashed with signal 11\n';

test('accepts only the recorded crash after a completed export', () => {
    assert.equal(classifyExport(0, complete, ''), 'success');
    assert.equal(classifyExport(3221225477, complete, crash), 'crash');
    assert.equal(classifyExport(-1073741819, complete, crash), 'crash');
    assert.throws(() => classifyExport(3221225477, '', crash));
    assert.throws(() => classifyExport(1, complete, crash));
    assert.throws(() => classifyExport(3221225477, complete, 'another crash'));
    assert.throws(() => classifyExport(3221225477, complete, `${crash}ERROR: export failed`));
    assert.throws(() => classifyExport(0, complete, 'SCRIPT ERROR: failed'));
});
