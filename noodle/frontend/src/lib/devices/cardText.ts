import { formatState, type Device, type Entity } from '../api.ts';
import { agoText } from './clock.svelte.ts';
import { fieldsOf, isMotion } from './kinds.ts';
import { COLORS, type CardColor, type CardRule, type CardSlot } from './cardDesign.ts';

/** What a component shows when its text and number format are applied. Pure: the card (and the designer's
 * preview) call it with the device as it is now. */

/** A field's value as text, in the slot's number format when it is a number. */
export function valueText(e: Entity | undefined, slot: Pick<CardSlot, 'decimals' | 'unit' | 'thousands'>): string {
	if (!e) return '–';
	if (typeof e.state !== 'number') return formatState(e);
	const n = slot.decimals !== undefined ? e.state.toFixed(slot.decimals) : String(Math.round(e.state * 100) / 100);
	const grouped = slot.thousands
		? Number(n).toLocaleString(undefined, { minimumFractionDigits: slot.decimals ?? 0, maximumFractionDigits: slot.decimals ?? 2 })
		: n;
	const unit = slot.unit !== undefined ? slot.unit : (e.unit ?? '');
	return unit ? `${grouped} ${unit}` : grouped;
}

/** The unit a number is shown with (the field's, unless the slot has its own). */
export const unitOf = (e: Entity | undefined, slot: Pick<CardSlot, 'unit'>) => (slot.unit !== undefined ? slot.unit : (e?.unit ?? ''));

function timeText(ts: number | null | undefined, how: string, now: number): string {
	if (!ts) return '–';
	if (how === 'clock') return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	if (how === 'datetime') return new Date(ts * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
	return agoText(ts, now, '–');
}

/** The values a template can show, for the designer's picker. A field of the device is written by its key: {motion}. */
export const TOKENS = [
	{ token: '{value}', label: 'This value' },
	{ token: '{name}', label: 'Field name' },
	{ token: '{unit}', label: 'Unit' },
	{ token: '{device}', label: 'Device name' },
	{ token: '{changed:ago}', label: 'Changed (5m ago)' },
	{ token: '{changed:clock}', label: 'Changed (clock time)' },
	{ token: '{changed:datetime}', label: 'Changed (date and time)' },
	{ token: '{seen:ago}', label: 'Last seen (5m ago)' },
	{ token: '{seen:clock}', label: 'Last seen (clock time)' }
];
const slug = (t: string) => t.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
export { fieldsOf };

/** A colour in a template: one of the named ones (success, warning ...) or a CSS colour of your own: hex (#3b82f6, #3b82f680)
 * or rgb(), rgba(), hsl(), hsla() (only digits, %, dots, commas, spaces and slashes inside, so nothing else can get in). */
export const isHex = (c?: string) => !!c && (/^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i.test(c) || /^(rgb|rgba|hsl|hsla)\(\s*[0-9.,%\s/]+(deg)?[0-9.,%\s/]*\)$/i.test(c));
const isColor = (c?: string) => !!c && (c in COLORS || isHex(c));

/** A field of the device by the name a template uses: `occupancy` or `device.occupancy`, either the key or the name as shown. */
export function findField(device: Device, ref: string): Entity | undefined {
	return locate(device, ref)?.entity;
}
/** The same, with the device the field belongs to (a graph needs both). */
export function locate(device: Device, ref: string): { device: Device; entity: Entity } | undefined {
	const own = (d: Device, n: string) => { const all = fieldsOf(d); const f = all.find((x) => x.key === n) ?? all.find((x) => slug(x.name) === slug(n)); return f && { device: d, entity: f }; };
	// another device's field: `living_room_lamp.brightness` (the device by its name or id, then the field)
	const m = /^([^.]+)\.(.+)$/.exec(ref);
	if (m && m[1] !== 'device') {
		const other = devicesNow().find((d) => d.id === m[1] || slug(d.name) === slug(m[1]));
		const f = other && own(other, m[2]);
		if (f) return f;
	}
	return own(device, ref.replace(/^device\./, ''));
}
/** `{device.brightness.history}`, `{lamp.temperature.history.24h}`, `{device.power.history.3d bars}`: a graph of a field's
 * last hours (5 h unless told: .1h .24h .3d ...; a line unless "bars"). In a Graph component it is the graph's data; in
 * other text it is drawn small where it stands. */
export function graphOf(device: Device, body: string): Part['graph'] | undefined {
	const m = /^(\S+?)\.history(?:\.(\d+)([hd]))?((?:\s+\S+)*)$/.exec(body.trim());
	if (!m) return undefined;
	const at = locate(device, m[1]);
	if (!at) return undefined;
	const opts = m[4].trim().split(/\s+/).filter(Boolean);
	const old = opts.map((o) => /^(\d+)([hd])$/.exec(o)).find(Boolean); // the first spelling: {x.history 24h}
	const n = m[2] ? [m[2], m[3]] : old ? [old[1], old[2]] : null;
	const hours = n ? Math.min(336, Math.max(1, Number(n[0]) * (n[1] === 'd' ? 24 : 1))) : 5;
	return { deviceId: at.device.id, key: at.entity.key, hours, bars: opts.includes('bars') };
}
let devicesNow: () => Device[] = () => [];
/** Where a template finds the other devices (the app gives it the live list). */
export const setDevices = (list: () => Device[]) => { devicesNow = list; };
/** How a template names another device's field: `living_room_lamp.brightness` (the field by its key when names clash). */
export function otherRef(device: Device, f: Pick<Entity, 'key' | 'name'>): string {
	const s = slug(f.name);
	const clash = !s || s === 'name' || device.entities.filter((x) => slug(x.name) === s).length > 1;
	return `${slug(device.name) || device.id}.${clash ? f.key : s}`;
}
/** How the designer writes a field: `device.occupancy` from its name, or from its key when two fields read alike. */
export function fieldName(device: Device, f: Pick<Entity, 'key' | 'name'>): string {
	const s = slug(f.name);
	const clash = !s || s === 'name' || device.entities.filter((x) => slug(x.name) === s).length > 1;
	return `device.${clash ? f.key : s}`;
}
export const fieldToken = (device: Device, f: Pick<Entity, 'key' | 'name'>) => `{${fieldName(device, f)}}`;

// ---- the template language -------------------------------------------------------------------------------------
// Text with {values} in it, and blocks:   {if motion == true} Motion {:else if temp > 20} Warm {:else} Quiet {/if}
// {color warning}, {icon motion} and {hide} (usually inside a block) style the component.
// Inline: {color success}green words{/color}, {b}bold{/b}, {i}italic{/i}, {u}underlined{/u} style just the words between.
// A condition can use: field keys, value, name, device, unit; numbers, 'text', true, false; == != > < >= <=; and or not ( ).

type Val = string | number | boolean | undefined;
type Expr = (get: (name: string) => Val) => Val;
type IfNode = { t: 'if'; branches: { cond: Expr | null; kids: Node[] }[] };
type Node = { t: 'text'; s: string } | { t: 'span'; what: 'color' | 'b' | 'i' | 'u' | 'size'; arg: string; on: boolean } | { t: 'out'; s: string } | { t: 'set'; what: 'color' | 'icon' | 'hide' | 'bg' | 'fill'; arg: string } | IfNode;

const YES = ['on', 'true', 'yes'];
const NO = ['off', 'false', 'no'];
const word = (v: unknown) => String(v).trim().toLowerCase();
const num = (v: Val) => (typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN);
const truthy = (v: Val) => (typeof v === 'number' ? v !== 0 : typeof v === 'string' ? v !== '' && !NO.includes(word(v)) : !!v);
/** on/off words equal true/false; numbers equal numbers; everything else compares as lower-case text */
function looseEqual(a: Val, b: Val): boolean {
	if (a === undefined || b === undefined) return false;
	if (typeof a === 'boolean' || typeof b === 'boolean') {
		const bool = (v: Val) => (typeof v === 'boolean' ? v : YES.includes(word(v)) ? true : NO.includes(word(v)) ? false : undefined);
		return bool(a) !== undefined && bool(a) === bool(b);
	}
	if (typeof a === 'number' || typeof b === 'number') return num(a) === num(b);
	return word(a) === word(b);
}

function compile(src: string): Expr {
	const toks = src.match(/'[^']*'|"[^"]*"|>=|<=|==|!=|&&|\|\||[()<>!]|[^\s()<>!=&|'"]+/g) ?? [];
	let p = 0;
	const isOp = (...ops: string[]) => ops.includes(toks[p]);
	function primary(): Expr {
		const t = toks[p++];
		if (t === undefined) throw new Error('a value is missing');
		if (t === '(') {
			const e = or();
			if (toks[p++] !== ')') throw new Error('missing )');
			return e;
		}
		if (t === '!' || t === 'not') {
			const e = primary();
			return (g) => !truthy(e(g));
		}
		if (t[0] === "'" || t[0] === '"') return () => t.slice(1, -1);
		if (/^-?\d+(\.\d+)?$/.test(t)) return () => Number(t);
		if (t === 'true') return () => true;
		if (t === 'false') return () => false;
		// a word that is not a field stands for itself, so  presence == home  works
		return (g) => g(t) ?? (/^[A-Za-z]+$/.test(t) ? t : undefined);
	}
	function compare(): Expr {
		const a = primary();
		if (!isOp('==', '!=', '>', '<', '>=', '<=', 'is')) return a;
		const op = toks[p++];
		let neg = op === '!=';
		if (op === 'is' && toks[p] === 'not') { p++; neg = true; }
		const b = primary();
		return (g) => {
			const x = a(g), y = b(g);
			const r = op === '>' ? num(x) > num(y) : op === '<' ? num(x) < num(y) : op === '>=' ? num(x) >= num(y) : op === '<=' ? num(x) <= num(y) : looseEqual(x, y);
			return neg ? !r : r;
		};
	}
	function and(): Expr {
		let a = compare();
		while (isOp('&&', 'and')) { p++; const l = a, r = compare(); a = (g) => truthy(l(g)) && truthy(r(g)); }
		return a;
	}
	function or(): Expr {
		let a = and();
		while (isOp('||', 'or')) { p++; const l = a, r = and(); a = (g) => truthy(l(g)) || truthy(r(g)); }
		return a;
	}
	const e = or();
	if (p < toks.length) throw new Error(`"${toks[p]}" is not expected here`);
	return e;
}

const parsed = new Map<string, { nodes: Node[]; error?: string }>();
/** Read a template into text, values and blocks. A mistake does not throw: it is reported and the rest still shows. */
export function parseTemplate(src: string): { nodes: Node[]; error?: string } {
	const hit = parsed.get(src);
	if (hit) return hit;
	const root: Node[] = [];
	const stack: { kids: Node[]; node?: IfNode }[] = [{ kids: root }];
	let error: string | undefined;
	const fail = (m: string) => (error ??= m);
	const text = (s: string) => { if (s) stack[stack.length - 1].kids.push({ t: 'text', s }); };
	const cond = (code: string, what: string): Expr => {
		try { return compile(code); } catch (e) { fail(`${what}: ${(e as Error).message}`); return () => false; }
	};
	// when the template closes a colour with {/color}, {color x} colours the words up to it instead of the whole component
	const spanColors = /\{\/color\}/.test(src);
	// two easy mistakes that would otherwise just show up as odd text
	const unclosed = /\{(?:if|:else|\/if|bg|fill|color|icon|size)\b[^{}]*(?=\{|$)/.exec(src);
	if (unclosed) fail(`A { is never closed: "${unclosed[0].trim().slice(0, 40)}" needs a } at the end.`);
	if (/\{else\b/.test(src)) fail('Write {:else} or {:else if …} with a colon.');
	const re = /\{([^{}]*)\}/g;
	let last = 0;
	for (let m = re.exec(src); m; m = re.exec(src)) {
		const body = m[1].trim();
		const style = /^(color|icon|bg|fill)\s+\S.*$|^hide$/.test(body);
		const inline = /^\/?[biu]$|^\/(color|size)$|^size\s+\d+$/.exec(body) ?? (spanColors ? /^color\s+\S.*$/.exec(body) : null);
		if (inline) {
			text(src.slice(last, m.index));
			const on = !body.startsWith('/');
			const [what, ...arg] = body.replace(/^\//, '').split(/\s+/);
			stack[stack.length - 1].kids.push({ t: 'span', what: what as 'color' | 'b' | 'i' | 'u' | 'size', arg: arg.join(' '), on });
			last = re.lastIndex;
			continue;
		}
		if (!style && !/^(if\b|:else\b|\/if$)/.test(body)) {
			// a value: worked out when it is shown (one that is not known stays as typed)
			text(src.slice(last, m.index));
			stack[stack.length - 1].kids.push({ t: 'out', s: body });
			last = re.lastIndex;
			continue;
		}
		// a tag alone on its line takes the line break with it
		text(src.slice(last, m.index).replace(/[ \t]*\r?\n[ \t]*$/, ''));
		const after = /^[ \t]*\r?\n/.exec(src.slice(re.lastIndex));
		last = re.lastIndex += after ? after[0].length : 0;
		const top = stack[stack.length - 1];
		if (style) {
			const [what, ...arg] = body.split(/\s+/);
			top.kids.push({ t: 'set', what: what as 'color' | 'icon' | 'hide' | 'bg' | 'fill', arg: arg.join(' ') });
		} else if (body.startsWith('if')) {
			const node: IfNode = { t: 'if', branches: [{ cond: cond(body.slice(2), '{if}'), kids: [] }] };
			top.kids.push(node);
			stack.push({ kids: node.branches[0].kids, node });
		} else if (body.startsWith(':else')) {
			const e = /^:else(?:\s+if\b([\s\S]*))?$/.exec(body);
			if (!top.node) fail('{:else} needs an {if} before it');
			else if (!e) fail('{:else} takes no condition, write {:else if …}');
			else {
				const branch = { cond: e[1] === undefined ? null : cond(e[1], '{:else if}'), kids: [] as Node[] };
				top.node.branches.push(branch);
				top.kids = branch.kids;
			}
		} else if (stack.length === 1) fail('{/if} needs an {if} before it');
		else stack.pop();
	}
	text(src.slice(last));
	if (stack.length > 1) fail('An {if} is not closed, add {/if}');
	const out = { nodes: root, error };
	if (parsed.size > 200) parsed.clear();
	parsed.set(src, out);
	return out;
}

/** A stretch of the text with its own look, when the template styles words ({color x}…{/color}, {b}…{/b}). */
export type Part = { text: string; graph?: { deviceId: string; key: string; hours: number; bars: boolean }; color?: string; size?: number; bold?: boolean; italic?: boolean; underline?: boolean };
export type Rendered = { text: string; parts?: Part[]; color?: string; bg?: string; fill?: string; icon?: string; hide: boolean; error?: string };

/** The template with the device's values in it. */
export function renderTemplate(template: string, device: Device, e: Entity | undefined, slot: CardSlot, now: number): Rendered {
	const { nodes, error } = parseTemplate(template);
	const field = (k: string) => findField(device, k);
	const shown = (f: Entity) => valueText(f, f.key === e?.key ? slot : {});
	const get = (name: string): Val => {
		if (name === 'value') return e?.state ?? undefined;
		if (name === 'name') return slot.label || e?.name || '';
		if (name === 'unit') return unitOf(e, slot);
		if (name === 'device' || name === 'device.name') return device.name;
		return field(name)?.state ?? undefined;
	};
	function out(s: string): string | null {
		const [name, arg] = s.split(/:(.*)/s);
		switch (name) {
			case 'value': return valueText(e, { ...slot, unit: '' }).trim();
			case 'name': return slot.label || e?.name || '';
			case 'unit': return unitOf(e, slot);
			case 'device': case 'device.name': return device.name;
			case 'changed': return timeText(e?.changed, arg ?? 'ago', now);
			case 'seen': return timeText(device.last_seen, arg ?? 'ago', now);
			case 'field': { const f = field(arg ?? ''); return f ? shown(f) : null; }
		}
		const f = field(s);
		return f ? shown(f) : null;
	}
	const res: Rendered = { text: '', hide: false, error };
	const parts: Part[] = [];
	const open: { what: string; arg: string }[] = [];
	/** the look of the words being written now ({color x}, {size n}, {b} ...) */
	const addStyle = (): Omit<Part, 'text'> => {
		const color = [...open].reverse().find((o) => o.what === 'color' && isColor(o.arg))?.arg;
		const size = Number([...open].reverse().find((o) => o.what === 'size')?.arg);
		return { ...(color ? { color } : {}), ...(size >= 8 && size <= 96 ? { size } : {}), ...(open.some((o) => o.what === 'b') ? { bold: true } : {}), ...(open.some((o) => o.what === 'i') ? { italic: true } : {}), ...(open.some((o) => o.what === 'u') ? { underline: true } : {}) };
	};
	const add = (t: string) => {
		if (t) parts.push({ text: t, ...addStyle() });
	};
	function run(list: Node[]) {
		const depth = open.length; // a style left open ends with its block
		for (const n of list) {
			if (n.t === 'text') add(n.s);
			else if (n.t === 'out') {
					const g = graphOf(device, n.s);
					if (g) parts.push({ text: '', graph: g, ...(addStyle()) });
					else add(out(n.s) ?? `{${n.s}}`);
				}
			else if (n.t === 'span') {
				if (n.on) open.push({ what: n.what, arg: n.arg });
				else { const i = open.map((o) => o.what).lastIndexOf(n.what); if (i >= 0) open.splice(i, 1); }
			} else if (n.t === 'set') {
				if (n.what === 'hide') res.hide = true;
				else if (n.what === 'color' && isColor(n.arg)) res.color = n.arg;
				else if (n.what === 'bg' && isColor(n.arg)) res.bg = n.arg;
				else if (n.what === 'fill' && isColor(n.arg)) res.fill = n.arg;
					else if (n.what === 'icon') res.icon = n.arg;
			} else {
				const b = n.branches.find((x) => {
					try { return x.cond === null || truthy(x.cond(get)); } catch { return false; }
				});
				if (b) run(b.kids);
			}
		}
		open.length = depth;
	}
	run(nodes);
	if (parts.length) parts[0].text = parts[0].text.trimStart();
	if (parts.length) parts[parts.length - 1].text = parts[parts.length - 1].text.trimEnd();
	const visible = parts.filter((p) => p.text || p.graph);
	res.text = visible.map((p) => p.text).join('');
	if (visible.some((p) => p.graph || p.color || p.size || p.bold || p.italic || p.underline)) res.parts = visible;
	return res;
}

// ---- rules from the first version (a visual list), still read and shown; the designer turns them into a template ----
/** Whether an old rule's condition holds for the device now. A field that is gone or has no value matches nothing. */
export function ruleMatches(rule: CardRule, device: Device, slot: CardSlot): boolean {
	const e = device.entities.find((x) => x.key === (rule.field || slot.key));
	if (!e || e.state === null || e.state === undefined) return false;
	const n = typeof e.state === 'number' ? e.state : NaN;
	switch (rule.op) {
		case 'is': return looseEqual(e.state, rule.value);
		case 'not': return !looseEqual(e.state, rule.value);
		case 'above': return n > Number(rule.value);
		case 'below': return n < Number(rule.value);
		case 'between': return n >= Number(rule.value) && n <= Number(rule.value2 ?? NaN);
	}
}

/** What a component's text box shows before anybody wrote anything: the template that gives the look the component
 * has now, so there is a working example to learn from and change. Nothing is saved until it is edited. A switch and a
 * knob show no text, so theirs is empty. */
export function defaultTemplate(slot: CardSlot, device: Device, source: Device = device): string {
	const e = fieldsOf(source).find((x) => x.key === slot.key);
	// a graph is written as what it draws: {device.brightness.history}
	if (e && slot.component === 'value' && ['line', 'bars', 'spark'].includes(slot.style ?? '')) return `{${source.id === device.id ? fieldName(device, e) : otherRef(source, e)}.history}`;
	if (!e || slot.component === 'text' || slot.component === 'switch' || slot.component === 'knob') return '';
	if (slot.component === 'button') return slot.label || (slot.action ? slot.action.replace(/_press$/, '').replaceAll('_', ' ') : e.name.replace(/^Button\s*/i, '') || e.name);
	const field = source.id === device.id ? fieldName(device, e) : otherRef(source, e);
	// on / off fields light up: green for motion, amber for the rest
	if (typeof e.state === 'boolean' && slot.component === 'value')
		return `{if ${field} == true}\n{color ${isMotion(e) ? 'success' : 'warning'}}{${field}}\n{:else}\n{${field}}\n{/if}`;
	return `{${field}}`;
}

/** The old rules as a template that does the same. */
export function rulesToTemplate(slot: CardSlot, device: Device): string {
	const lit = (v: string | number) => (typeof v === 'number' || /^-?\d+(\.\d+)?$/.test(v) ? String(v) : `'${String(v).replace(/'/g, '')}'`);
	const parts = (slot.rules ?? []).map((r, i) => {
		const key = r.field || slot.key;
		const f = findField(device, key);
		const name = f ? fieldName(device, f) : `device.${key}`;
		const bool = typeof f?.state === 'boolean';
		const v = bool ? (YES.includes(word(r.value)) ? 'true' : 'false') : lit(r.value);
		const c = r.op === 'is' ? `${name} == ${v}` : r.op === 'not' ? `${name} != ${v}` : r.op === 'above' ? `${name} > ${v}` : r.op === 'below' ? `${name} < ${v}` : `${name} >= ${v} and ${name} <= ${r.value2 ?? 0}`;
		const set = [r.then.color && `{color ${r.then.color}}`, r.then.icon && `{icon ${r.then.icon}}`, r.then.hide && '{hide}'].filter(Boolean).join('');
		return `{${i ? ':else ' : ''}if ${c}}\n${set}${r.then.text ?? '{value}'}\n`;
	});
	return `${parts.join('')}{:else}\n${slot.template ?? (slot.key ? '{value}' : '')}\n{/if}`;
}

/** The CSS for a component's background colour (a solid mix, so it covers whatever the component draws behind it). */
export const backgroundStyle = (c?: string) => (!c ? '' : isHex(c) ? `background:${c};` : `background: color-mix(in oklab, var(--color-${c}) 35%, var(--color-base-100));`);

export type Shown = {
	/** the component's own background colour ({bg success}) */
	bg?: string;
	/** the colour of what fills or draws (a slider's or bar's fill, a gauge, a graph, the power button when on): {fill success} */
	fill?: string;
	/** the text in stretches of their own look, when the template styles words */
	parts?: Part[];
	/** the text to show instead of the field's own; undefined: show the field as usual */
	text?: string;
	color?: string;
	icon?: string;
	hide: boolean;
	/** a mistake in the template, for the designer to point out */
	error?: string;
};

/** Apply the component's text template (and, for designs from before templates had blocks, its first matching rule). */
export function resolve(slot: CardSlot, device: Device, now: number, from: Device = device): Shown {
	// the component's own field may belong to another device; `device` in the text stays the card's device
	const e = fieldsOf(from).find((x) => x.key === slot.key);
	const rule = (slot.rules ?? []).find((r) => ruleMatches(r, device, slot));
	const source = rule?.then.text ?? slot.template;
	const r = source !== undefined ? renderTemplate(source, device, e, slot, now) : undefined;
	return {
		text: r?.text,
		parts: rule ? undefined : r?.parts,
		bg: rule ? undefined : r?.bg,
		fill: rule ? undefined : r?.fill,
		color: rule?.then.color ?? r?.color ?? slot.color,
		icon: rule?.then.icon ?? r?.icon,
		hide: !!rule?.then.hide || !!r?.hide,
		error: r?.error
	};
}
