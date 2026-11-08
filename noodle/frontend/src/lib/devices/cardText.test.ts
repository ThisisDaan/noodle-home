// @ts-nocheck (run with: bun test)
import { expect, mock, test } from 'bun:test';

mock.module('../api.ts', () => ({ formatState: (e: { state: unknown }) => (e.state === true ? 'On' : e.state === false ? 'Off' : String(e.state)) }));
mock.module('./clock.svelte.ts', () => ({ agoText: () => '5m ago' }));
mock.module('./cardDesign.ts', () => ({ COLORS: { warning: {}, success: {}, error: {} } }));

const { renderTemplate, parseTemplate, rulesToTemplate, resolve, setDevices, defaultTemplate, fieldsOf } = await import('./cardText.ts');

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
	expect(run('{color warning}Hot')).toMatchObject({ text: 'Hot', color: 'warning' });
	expect(run('{color warning}Hot').parts).toBeUndefined();
});

test('a component sets its own background', () => {
	const s = slot('{if motion == true}\n{bg success}\n{:else}\n{bg error}\n{/if}')
	expect(resolve(s, device(true), 0).bg).toBe('success');
	expect(resolve(s, device(false), 0).bg).toBe('error');
	expect(resolve(slot('plain'), device(true), 0).bg).toBeUndefined();
});

test('font size on the selected words', () => {
	const r = run('Big {size 24}{motion}{/size} small');
	expect(r.parts?.map((p) => [p.text, p.size])).toEqual([['Big ', undefined], ['On', 24], [' small', undefined]]);
});

test('a template reads another device by its name', () => {
	setDevices(() => [{ id: 'hue:1', name: 'Living room lamp', entities: [{ key: 'brightness', name: 'Brightness', state: 80 }] }] as never);
	expect(run('Lamp {living_room_lamp.brightness}%').text).toBe('Lamp 80%');
	expect(run('{if living_room_lamp.brightness > 50}Bright{:else}Dim{/if}').text).toBe('Bright');
	expect(run('{device.motion}').text).toBe('On'); // the device's own fields still work
	setDevices(() => []);
});

test('the default template of a component works and says what it shows now', () => {
	const d = device(true);
	const base = { x: 0, y: 0, w: 1, h: 1 };
	const on = defaultTemplate({ ...base, component: 'value', key: 'motion' } as never, d);
	expect(on).toContain('{if device.motion == true}');
	expect(parseTemplate(on).error).toBeUndefined();
	expect(renderTemplate(on, d, d.entities[0], { ...base, component: 'value', key: 'motion' } as never, 0).text).toBe('On');
	expect(defaultTemplate({ ...base, component: 'slider', key: 'temp' } as never, d)).toBe('{device.temperature}');
	expect(defaultTemplate({ ...base, component: 'switch', key: 'motion' } as never, d)).toBe('');
});

test('{fill colour} sets the fill, apart from the text colour', () => {
	const r = renderTemplate('{fill success}{color error}x', device(true), undefined, slot('x'), 0);
	expect(r.fill).toBe('success');
	expect(r.color).toBe('error');
	expect(r.text).toBe('x');
});

test('hex colours work anywhere a colour does, and a light has a brightness field', () => {
	const lamp = { name: 'Lamp', last_seen: 1, entities: [{ key: 'light', name: 'Light', kind: 'light', state: true, brightness: 80 }] } as never;
	const t = '{if device.brightness > 50}{bg #112233}{fill #abc}{color #ff0000}{:else}{bg success}{/if}{device.light}';
	const r = renderTemplate(t, lamp, undefined, slot(t), 0);
	expect(r.bg).toBe('#112233');
	expect(r.fill).toBe('#abc');
	expect(r.color).toBe('#ff0000');
	expect(fieldsOf(lamp).find((f) => f.key === 'brightness').state).toBe(80);
	expect(renderTemplate(t, { ...lamp, entities: [{ ...lamp.entities[0], brightness: 20 }] }, undefined, slot(t), 0).bg).toBe('success');
});

test('rgba and hsl colours work, and nothing else gets into a style', () => {
	const r = renderTemplate('{fill rgba(0, 0, 0, 0)}{bg hsl(120 50% 40%)}{color url(x)}x', device(true), undefined, slot('x'), 0);
	expect(r.fill).toBe('rgba(0, 0, 0, 0)');
	expect(r.bg).toBe('hsl(120 50% 40%)');
	expect(r.color).toBeUndefined();
});

test('two easy mistakes are pointed out', () => {
	const nl = String.fromCharCode(10);
	expect(parseTemplate(['{if device.temp > 1', 'x', '{/if}'].join(nl)).error).toContain('never closed');
	expect(parseTemplate(['{if device.temp > 1}', 'x', '{else}', 'y', '{/if}'].join(nl)).error).toContain('colon');
	expect(parseTemplate(['{if device.temp > 1}', 'x', '{:else}', 'y', '{/if}'].join(nl)).error).toBeUndefined();
});

test('{field.history} draws a small graph in the text, of this or another device', () => {
	const lamp = { id: 'lamp1', name: 'Lamp', last_seen: 1, entities: [{ key: 'light', name: 'Light', state: true, kind: 'light', brightness: 50 }] };
	setDevices(() => [lamp as never]);
	const r = run('Level {device.temp.history.24h bars} now {lamp.brightness.history}', device(true));
	const graphs = r.parts!.filter((p) => p.graph).map((p) => p.graph);
	expect(graphs[0]).toEqual({ deviceId: undefined, key: 'temp', hours: 24, bars: true });
	expect(graphs[1]).toEqual({ deviceId: 'lamp1', key: 'brightness', hours: 5, bars: false });
	expect(run('{nothing.history}').text).toBe('{nothing.history}');
});
