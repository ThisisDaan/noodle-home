// @ts-nocheck (run with: bun test)
import { expect, test } from 'bun:test';
import { readFileSync } from 'fs';
import { known, THEMES } from './theme.ts';

const css = readFileSync(new URL('../app.css', import.meta.url), 'utf8');
const config = readFileSync(new URL('../../../backend/noodle/config.py', import.meta.url), 'utf8');

test('every theme in the list is defined in app.css', () => {
	const enabled = css.match(/themes: ([^;]+);/)[1].split(',').map((t) => t.trim());
	for (const t of THEMES) expect(enabled.includes(t.id) || css.includes(`name: '${t.id}'`)).toBe(true);
});

test('the hub accepts the same themes as the picker offers', () => {
	const backend = [...config.match(/THEMES = \(([^)]+)\)/)[1].matchAll(/"([\w-]+)"/g)].map((m) => m[1]);
	expect(backend).toEqual(THEMES.map((t) => t.id));
});

test('an unknown theme means Noodle', () => {
	expect(known('dracula')).toBe('dracula');
	expect(known('no-such-theme')).toBe('');
	expect(known({ background: '#000000' })).toBe('');
	expect(known(undefined)).toBe('');
});
