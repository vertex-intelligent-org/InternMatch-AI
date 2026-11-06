import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = new URL('../src/', import.meta.url);
const decoder = new TextDecoder('utf-8', { fatal: true });
const dictionaries = ['en', 'tr', 'ar'].map(locale => JSON.parse(decoder.decode(readFileSync(new URL(`locales/${locale}.json`, root)))));

test('every source file is strict UTF-8 without BOM, replacement glyphs or null bytes', () => {
  function walk(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const file = join(dir, entry.name);
      if (entry.isDirectory()) { walk(file); continue; }
      const bytes = readFileSync(file);
      assert.notEqual(bytes.subarray(0, 3).toString('hex'), 'efbbbf', file);
      const text = decoder.decode(bytes);
      assert.ok(!text.includes('\ufffd') && !text.includes('\0'), file);
    }
  }
  walk(fileURLToPath(root));
});

test('all languages have exactly the same non-empty translation keys', () => {
  const keys = Object.keys(dictionaries[0]).sort();
  for (const dictionary of dictionaries) {
    assert.deepEqual(Object.keys(dictionary).sort(), keys);
    for (const value of Object.values(dictionary)) assert.ok(typeof value === 'string' && value.trim());
  }
});

test('source-derived mobile and parity dictionaries have identical translated keys', () => {
  for (const folder of ['mobile', 'parity', 'brand', 'auth', 'student', 'workspace']) {
    const values = ['en', 'tr', 'ar'].map(locale => JSON.parse(decoder.decode(readFileSync(new URL(`locales/${folder}/${locale}.json`, root)))));
    const keys = Object.keys(values[0]).sort();
    for (const dictionary of values) {
      assert.deepEqual(Object.keys(dictionary).sort(), keys);
      for (const value of Object.values(dictionary)) {
        assert.ok(typeof value === 'string' && value.trim());
        assert.ok(!/\?{2,}|\ufffd|Ã¼|Ä±|Ø§|Ù„/.test(value));
      }
    }
  }
});

test('Arabic and Turkish retain real Unicode text without question-mark corruption', () => {
  const turkish = Object.values(dictionaries[1]).join('\n');
  const arabic = Object.values(dictionaries[2]).join('\n');
  for (const letter of 'çğıöşüİ') assert.ok(turkish.includes(letter), letter);
  assert.equal(dictionaries[1].language, 'Dil');
  assert.equal(dictionaries[1].student, 'Öğrenci');
  assert.equal(dictionaries[2].language, 'اللغة');
  assert.equal(dictionaries[2].employer, 'صاحب عمل');
  assert.ok((arabic.match(/[\u0600-\u06ff]/g) ?? []).length > 1500);
  for (const text of [turkish, arabic]) {
    assert.ok(!/\?{2,}|\ufffd|Ã¼|Ã¶|Ä±|ÅŸ|Ø§|Ù„/.test(text));
  }
});
