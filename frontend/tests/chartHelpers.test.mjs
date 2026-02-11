import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildChecklistSummary,
  buildEmptyChecklist,
  buildNotesPreview,
  chartHasFlag,
} from '../src/lib/chartHelpers.js';

test('buildEmptyChecklist initializes all values to false', () => {
  const checklist = buildEmptyChecklist();
  assert.ok(Object.values(checklist).every((value) => value === false));
});

test('buildChecklistSummary returns selected labels', () => {
  const summary = buildChecklistSummary({ red_candle: true, momentum_green: true });
  assert.match(summary, /Red Candle/);
  assert.match(summary, /MACD Positive/);
});

test('buildNotesPreview truncates long notes', () => {
  const preview = buildNotesPreview('x'.repeat(150));
  assert.equal(preview.length, 103);
  assert.ok(preview.endsWith('...'));
});

test('chartHasFlag handles missing checklist safely', () => {
  assert.equal(chartHasFlag({ checklist: { trend_bullish: true } }, 'trend_bullish'), true);
  assert.equal(chartHasFlag({}, 'trend_bullish'), false);
});
