import { formatState, type Device, type Entity } from '../api.ts';
import { agoText } from './clock.svelte.ts';
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
/** A field of the device by the name a template uses: `occupancy` or `device.occupancy`, either the key or the name as shown. */
export function findField(device: Device, ref: string): Entity | undefined {
	const n = ref.replace(/^device\./, '');
	return device.entities.find((x) => x.key === n) ?? device.entities.find((x) => slug(x.name) === slug(n));
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
type Node = { t: 'text'; s: string } | { t: 'span'; what: 'color' | 'b' | 'i' | 'u'; arg: string; on: boolean } | { t: 'out'; s: string } | { t: 'set'; what: 'color' | 'icon' | 'hide'; arg: string } | IfNode;

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
	const re = /\{([^{}]*)\}/g;
	let last = 0;
	for (let m = re.exec(src); m; m = re.exec(src)) {
		const body = m[1].trim();
		const style = /^(color|icon)\s+\S+$|^hide$/.test(body);
		const inline = /^\/?[biu]$|^\/color$/.exec(body) ?? (spanColors ? /^color\s+\S+$/.exec(body) : null);
		if (inline) {
			text(src.slice(last, m.index));
			const on = !body.startsWith('/');
			const [what, ...arg] = body.replace(/^\//, '').split(/\s+/);
			stack[stack.length - 1].kids.push({ t: 'span', what: what as 'color' | 'b' | 'i' | 'u', arg: arg.join(' '), on });
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
			top.kids.push({ t: 'set', what: what as 'color' | 'icon' | 'hide', arg: arg.join(' ') });
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
export type Part = { text: string; color?: CardColor; bold?: boolean; italic?: boolean; underline?: boolean };
export type Rendered = { text: string; parts?: Part[]; color?: CardColor; icon?: string; hide: boolean; error?: string };

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
	const add = (t: string) => {
		if (!t) return;
		const color = [...open].reverse().find((o) => o.what === 'color' && o.arg in COLORS)?.arg as CardColor | undefined;
		parts.push({ text: t, ...(color ? { color } : {}), ...(open.some((o) => o.what === 'b') ? { bold: true } : {}), ...(open.some((o) => o.what === 'i') ? { italic: true } : {}), ...(open.some((o) => o.what === 'u') ? { underline: true } : {}) });
	};
	function run(list: Node[]) {
		const depth = open.length; // a style left open ends with its block
		for (const n of list) {
			if (n.t === 'text') add(n.s);
			else if (n.t === 'out') add(out(n.s) ?? `{${n.s}}`);
			else if (n.t === 'span') {
				if (n.on) open.push({ what: n.what, arg: n.arg });
				else { const i = open.map((o) => o.what).lastIndexOf(n.what); if (i >= 0) open.splice(i, 1); }
			} else if (n.t === 'set') {
				if (n.what === 'hide') res.hide = true;
				else if (n.what === 'color' && n.arg in COLORS) res.color = n.arg as CardColor;
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
	const visible = parts.filter((p) => p.text);
	res.text = visible.map((p) => p.text).join('');
	if (visible.some((p) => p.color || p.bold || p.italic || p.underline)) res.parts = visible;
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

export type Shown = {
	/** the text in stretches of their own look, when the template styles words */
	parts?: Part[];
	/** the text to show instead of the field's own; undefined: show the field as usual */
	text?: string;
	color?: CardColor;
	icon?: string;
	hide: boolean;
	/** a mistake in the template, for the designer to point out */
	error?: string;
};

/** Apply the component's text template (and, for designs from before templates had blocks, its first matching rule). */
export function resolve(slot: CardSlot, device: Device, now: number): Shown {
	const e = device.entities.find((x) => x.key === slot.key);
	const rule = (slot.rules ?? []).find((r) => ruleMatches(r, device, slot));
	const source = rule?.then.text ?? slot.template;
	const r = source !== undefined ? renderTemplate(source, device, e, slot, now) : undefined;
	return {
		text: r?.text,
		parts: rule ? undefined : r?.parts,
		color: rule?.then.color ?? r?.color ?? slot.color,
		icon: rule?.then.icon ?? r?.icon,
		hide: !!rule?.then.hide || !!r?.hide,
		error: r?.error
	};
}
