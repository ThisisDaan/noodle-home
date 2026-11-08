// @ts-nocheck (run with: bun test)
import { expect, test } from 'bun:test';
import { parseRules, serializeRules } from './rules.ts';

const USER = `{if device.brightness > 50}
{bg success}
{fill success}
{device.brightness}
{:else if device.brightness >= 1}
{bg secondary}
{fill info}
{device.brightness}
{:else}
Off
{/if}`;

test('the brightness template reads as two rules and an otherwise', () => {
	const s = parseRules(USER)!;
	expect(s.rules.length).toBe(2);
	expect(s.rules[0].clauses).toEqual([{ field: 'device.brightness', op: '>', value: '50' }]);
	expect(s.rules[0].then).toEqual({ bg: 'success', fill: 'success', text: '{device.brightness}' });
	expect(s.rules[1].then).toEqual({ bg: 'secondary', fill: 'info', text: '{device.brightness}' });
	expect(s.otherwise.text).toBe('Off');
});

test('writing it out and reading it again gives the same rules', () => {
	const s = parseRules(USER)!;
	expect(parseRules(serializeRules(s))).toEqual(s);
});

test('and / or, text values, on/off', () => {
	const t = "{if motion == true and presence == 'home'}Hi{:else if temp < 5 or temp > 30}Extreme{:else}Fine{/if}";
	const s = parseRules(t)!;
	expect(s.rules[0]).toMatchObject({ join: 'and', clauses: [{ field: 'motion', op: '==', value: 'true' }, { field: 'presence', op: '==', value: 'home' }] });
	expect(s.rules[1].join).toBe('or');
	expect(parseRules(serializeRules(s))).toEqual(s);
});

test('hide and icon', () => {
	const s = parseRules('{if a == 1}{icon bell}{hide}{:else}x{/if}')!;
	expect(s.rules[0].then).toMatchObject({ icon: 'bell', hide: true });
});

test('plain text and empty text have no rules', () => {
	expect(parseRules('')).toEqual({ rules: [], otherwise: { text: '' } });
	expect(parseRules('{value} °C')!.otherwise.text).toBe('{value} °C');
	expect(serializeRules(parseRules('{bg warning}{value}')!)).toBe('{bg warning}{value}');
});

test('what the view cannot show stays in the code box', () => {
	expect(parseRules('{if a == 1}{if b == 2}x{/if}{/if}')).toBeNull();
	expect(parseRules('{if (a == 1 or b == 2) and c == 3}x{/if}')).toBeNull();
	expect(parseRules('{if not a}x{/if}')).toBeNull();
	expect(parseRules('{if a == 1 and b == 2 or c == 3}x{/if}')).toBeNull();
	expect(parseRules('before {if a == 1}x{/if}')).toBeNull();
	expect(parseRules('{if a == 1}x{/if} after')).toBeNull();
	expect(parseRules('{if a == 1}x{:else}y{:else if b == 1}z{/if}')).toBeNull();
});

test('a colour that closes with {/color} stays in the text', () => {
	const s = parseRules('{if a == 1}{color success}ok{/color}{:else}no{/if}')!;
	expect(s.rules[0].then.color).toBeUndefined();
	expect(s.rules[0].then.text).toBe('{color success}ok{/color}');
});
