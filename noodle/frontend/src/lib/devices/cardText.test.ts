// @ts-nocheck (run with: bun test)
import { expect, mock, test } from 'bun:test';

mock.module('../api.ts', () => ({ formatState: (e: { state: unknown }) => (e.state === true ? 'On' : e.state === false ? 'Off' : String(e.state)) }));
mock.module('./clock.svelte.ts', () => ({ agoText: () => '5m ago' }));
mock.module('./cardDesign.ts', () => ({ COLORS: { warning: {}, success: {}, error: {} } }));

const { renderTemplate, parseTemplate, rulesToTemplate, resolve } = await import('./cardText.ts');

const device = (motion: boolean, temp = 21) =>
	({ name: 'Hall', last_seen: 1, entities: [
		{ key: 'motion', name: 'Motion', state: motion, kind: 'binary' },
		{ key: 'temp', name: 'Temperature', state: temp, unit: '°C', kind: 'number' },
		{ key: 'presence', name: 'Presence', state: 'home' }
	] }) as never;
const slot = (template: string) => ({ x: 0, y: 0, w: 1, h: 1, component: 'text', key: '', template }) as never;
const run = (t: string, d = device(true)) => renderTemplate(t, d, undefined, slot(t), 0);

const BLOCK = `{if motion == true}
Motion detected
{:else}
no motion
{/if}`;

test('the if / else block from the request', () => {
	expect(run(BLOCK, device(true)).text).toBe('Motion detected');
	expect(run(BLOCK, device(false)).text).toBe('no motion');
	expect(run(BLOCK).error).toBeUndefined();
});

test('else if, comparisons, and/or/not, words', () => {
	const t = '{if motion}Move{:else if temp > 25 and not motion}Hot{:else if temp >= 20 && temp < 25}Warm {temp}{:else}Cold{/if}';
	expect(run(t, device(true)).text).toBe('Move');
	expect(run(t, device(false, 30)).text).toBe('Hot');
	expect(run(t, device(false, 21)).text).toBe('Warm 21 °C');
	expect(run(t, device(false, 5)).text).toBe('Cold');
	expect(run("{if presence == home}In{:else}Out{/if}").text).toBe('In');
	expect(run("{if presence is not 'away'}Here{/if}").text).toBe('Here');
	expect(run("{if motion == 'on'}On{/if}").text).toBe('On');
});

test('nested blocks and style tags', () => {
	const r = run('{if motion}{if temp > 20}{color warning}{icon motion}Hot move{/if}{/if}{if temp > 99}{hide}{/if}');
	expect(r).toMatchObject({ text: 'Hot move', color: 'warning', icon: 'motion', hide: false });
	expect(run('{hide}').hide).toBe(true);
});

test('values and unknown tags', () => {
	expect(run('{device}: {temp} {seen:ago} {nothing}').text).toBe('Hall: 21 °C 5m ago {nothing}');
});

test('mistakes are reported, the rest still shows', () => {
	expect(parseTemplate('{if motion}x').error).toContain('not closed');
	expect(parseTemplate('x{/if}').error).toContain('{/if}');
	expect(parseTemplate('{:else}').error).toContain('{:else}');
	expect(parseTemplate('{if motion ==}x{/if}').error).toContain('{if}');
	expect(run('{if motion}Yes{/if} done').text).toBe('Yes done');
	expect(run('{if motion}Yes').text).toBe('Yes');
});

test('old rules become a template that does the same', () => {
	const s = { x: 0, y: 0, w: 1, h: 1, component: 'value', key: 'motion', rules: [
		{ op: 'is', value: 'on', then: { text: 'Motion', color: 'warning' } },
		{ field: 'temp', op: 'between', value: 10, value2: 20, then: { text: 'Cool' } }
	] } as never;
	const t = rulesToTemplate(s, device(true));
	expect(parseTemplate(t).error).toBeUndefined();
	const plain = { ...(s as object), rules: undefined, template: t } as never;
	expect(resolve(plain, device(true), 0)).toMatchObject({ text: 'Motion', color: 'warning' });
	expect(resolve(plain, device(false, 15), 0).text).toBe('Cool');
	expect(resolve(plain, device(false, 30), 0).text).toBe('Off');
});

test('fields by key, by device.key and by the name as shown', () => {
	expect(run('{if device.motion == true}Y{:else}N{/if}').text).toBe('Y');
	expect(run('{device.temperature} / {device.temp} / {temperature}').text).toBe('21 °C / 21 °C / 21 °C');
	expect(run('{if device.temperature > 20}Warm{/if}').text).toBe('Warm');
	expect(run('{device.name}').text).toBe('Hall');
});

test('words coloured and styled inline', () => {
	const t = `{if device.motion == true}
{color success}Motion Detected{/color}
{:else}
{color error}No Motion{/color}
{/if}`;
	const on = run(t, device(true));
	expect(on.text).toBe('Motion Detected');
	expect(on.parts).toEqual([{ text: 'Motion Detected', color: 'success' }]);
	expect(run(t, device(false)).parts).toEqual([{ text: 'No Motion', color: 'error' }]);
	const mix = run('Temp: {b}{device.temp}{/b} {i}now{/i} {u}ok{/u} {color warning}!');
	expect(mix.text).toBe('Temp: 21 °C now ok !');
	expect(mix.parts?.map((p) => [p.text, p.color, p.bold, p.italic, p.underline])).toEqual([
		['Temp: ', undefined, undefined, undefined, undefined], ['21 °C', undefined, true, undefined, undefined], [' ', undefined, undefined, undefined, undefined],
		['now', undefined, undefined, true, undefined], [' ', undefined, undefined, undefined, undefined], ['ok', undefined, undefined, undefined, true],
		[' ', undefined, undefined, undefined, undefined], ['!', undefined, undefined, undefined, undefined]]);
	expect(mix.color).toBe('warning'); // no {/color} anywhere: the old meaning, the whole component
	expect(run('plain').parts).toBeUndefined();
	// without {/color} the old meaning holds: the colour is the component's
	expect(run('{color warning}Hot')).toMatchObject({ text: 'Hot', color: 'warning', parts: undefined });
});
