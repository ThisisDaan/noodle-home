import type { Device, Entity } from '../api.ts';
import { fieldsOf, contactEntity, deviceKind, isContact, isHumidity, isMotion, isPower, isTemperature, presenceEntity } from './kinds.ts';

/** How a device's card is designed: a size in dashboard cells (w x h) and components placed anywhere on the card's
 * fine grid, each with its own position, size and display style. Stored in the dashboard layout (backend main.py
 * CARD_* must say the same). A remote's buttons have their own look (DeviceFace) and no design. */
export type CardComponentType = 'switch' | 'value' | 'dial' | 'slider' | 'text' | 'button' | 'knob';
export type CardStyle = 'text-s' | 'text-m' | 'text-l' | 'chip' | 'icon' | 'gauge' | 'bar' | 'line' | 'bars' | 'spark';
export type CardColor = 'primary' | 'secondary' | 'accent' | 'success' | 'warning' | 'error' | 'info' | 'neutral';
export type RuleOp = 'is' | 'not' | 'above' | 'below' | 'between';
/** When `field` (default: the component's own) <op> value, then the component shows this instead; first match wins. */
export type CardRule = { field?: string; op: RuleOp; value: string | number; value2?: number; then: { text?: string; color?: CardColor; icon?: string; hide?: boolean } };
export type CardSlot = {
	x: number; y: number; w: number; h: number; component: CardComponentType;
	/** the device's field ('' for a label) */
	key: string;
	/** a reading only: the id of another device the field belongs to (default: this device) */
	device?: string;
	style?: CardStyle; label?: string; hours?: number;
	/** a button: which press it sends (default: the button's main one) */
	action?: string;
	/** the text, with {tokens} (see cardText.ts); without one the component shows its field as it always did */
	template?: string;
	/** number format */
	decimals?: number; unit?: string; thousands?: boolean;
	/** text style */
	bold?: boolean; italic?: boolean; underline?: boolean; align?: 'left' | 'center' | 'right'; color?: CardColor;
	rules?: CardRule[];
};
export type CardDesign = { w: number; h: number; slots: CardSlot[] };

/** Font sizes (px) the editor offers; a template can use any whole size from 8 to 96 with {size 24}…{/size}. */
export const FONT_SIZES = [10, 12, 14, 16, 18, 20, 24, 32, 40, 48, 64];
/** The three old text sizes are one "Text" now: the size is set in the editor. */
export const isTextStyle = (s?: CardStyle) => s === 'text-s' || s === 'text-m' || s === 'text-l';

/** Fine grid cells per dashboard cell, and the biggest card. */
export const PER_COL = 4;
export const PER_ROW = 2;
export const MAX_W = 4;
export const MAX_H = 4;
export const grid = (d: { w: number; h: number }) => ({ cols: d.w * PER_COL, rows: d.h * PER_ROW });

export const COMPONENTS: Record<CardComponentType, { label: string; hint: string; w: number; h: number }> = {
	switch: { label: 'Switch', hint: 'Tap to turn on or off', w: 1, h: 2 },
	value: { label: 'Reading', hint: 'Shows a value', w: 2, h: 2 },
	dial: { label: 'Dial', hint: 'Plus and minus for a number', w: 3, h: 2 },
	slider: { label: 'Slider', hint: 'Drag to set a number or brightness', w: 3, h: 2 },
	text: { label: 'Label', hint: 'Text you write, with values from the device in it', w: 3, h: 1 },
	button: { label: 'Button', hint: 'Tap to press a button of the device', w: 1, h: 2 },
	knob: { label: 'Knob', hint: "A remote's brighter and dimmer as a - knob +", w: 2, h: 2 }
};

/** The ways a reading can be shown. `numeric`: only for a number. */
export const STYLES: Record<CardStyle, { label: string; numeric?: boolean; plain?: boolean; graph?: boolean; w: number; h: number }> = {
	'text-s': { label: 'Small text', plain: true, w: 2, h: 1 },
	'text-m': { label: 'Text', plain: true, w: 2, h: 1 },
	'text-l': { label: 'Big text', plain: true, w: 2, h: 2 },
	chip: { label: 'Status', w: 4, h: 2 },
	icon: { label: 'Icon', w: 1, h: 2 },
	gauge: { label: 'Gauge', numeric: true, w: 2, h: 2 },
	bar: { label: 'Progress bar', numeric: true, w: 4, h: 1 },
	line: { label: 'Graph', numeric: true, graph: true, w: 4, h: 2 },
	bars: { label: 'Bar graph', numeric: true, graph: true, w: 4, h: 2 },
	spark: { label: 'Sparkline', numeric: true, graph: true, w: 3, h: 1 }
};

/** Hours of history a graph shows. */
export const HOURS = [1, 6, 24, 72, 168];
export const hoursLabel = (h: number) => (h < 48 ? `${h} h` : `${h / 24} days`);

/** The styles a field can be shown in: text, a status bar or an icon for anything (the text says what to show); a gauge,
 * bar or graph only for a number. */
export function stylesFor(e: Entity): CardStyle[] {
	const numeric = typeof e.state === 'number';
	return (Object.keys(STYLES) as CardStyle[]).filter((s) => !STYLES[s].numeric || numeric);
}

/** The style a reading gets when nobody chose one: a status bar for motion, doors, power and on/off, else big text. */
export const autoStyle = (e?: Entity): CardStyle =>
	e && (isMotion(e) || isContact(e) || isPower(e) || ['switch', 'fan', 'light'].includes(e.kind)) ? 'chip' : 'text-l';

/** Which fields of a device a component can show or control. */
export function compatible(component: CardComponentType, e: Entity): boolean {
	switch (component) {
		case 'switch': return e.kind === 'switch' || e.kind === 'light' || e.kind === 'fan';
		case 'value': return e.kind !== 'button';
		case 'dial': return e.kind === 'number' || e.kind === 'climate';
		case 'slider': return e.kind === 'number' || (e.kind === 'light' && e.brightness !== null);
		case 'text': return false;
		case 'button': return e.kind === 'button';
		case 'knob': return e.kind === 'button' && e.role === 'increase';
	}
}

/** What the editor offers to add: a component, and for a reading the style it starts in. */
export const PRESETS: { id: string; label: string; component: CardComponentType; style?: CardStyle }[] = [
	{ id: 'number', label: 'Number', component: 'value', style: 'text-l' },
	{ id: 'label', label: 'Text', component: 'text', style: 'text-m' },
	{ id: 'status', label: 'Status', component: 'value', style: 'chip' },
	{ id: 'graph', label: 'Graph', component: 'value', style: 'line' },
	{ id: 'bars', label: 'Bars', component: 'value', style: 'bars' },
	{ id: 'gauge', label: 'Gauge', component: 'value', style: 'gauge' },
	{ id: 'progress', label: 'Progress', component: 'value', style: 'bar' },
	{ id: 'icon', label: 'Icon', component: 'value', style: 'icon' },
	{ id: 'switch', label: 'Switch', component: 'switch' },
	{ id: 'slider', label: 'Slider', component: 'slider' },
	{ id: 'dial', label: 'Dial', component: 'dial' },
	{ id: 'button', label: 'Button', component: 'button' },
	{ id: 'knob', label: 'Knob', component: 'knob' }
];
/** Whether a preset has a field to work with on this device (a graph needs a number, a status bar does not). */
export function presetFields(device: Device, p: (typeof PRESETS)[number]): Entity[] {
	if (p.component === 'text') return [];
	return fieldsOf(device).filter((e) => compatible(p.component, e) && (!p.style || stylesFor(e).includes(p.style)));
}
/** Where a preset gets its field: this device if it has one, else (a reading only) any other device, since a card can show
 * another device's numbers. `device` is the other device's id, left out for this one. */
export function presetSource(device: Device, p: (typeof PRESETS)[number], all: Device[]): { device?: string; entity: Entity; used?: Set<string> } | undefined {
	const own = presetFields(device, p);
	if (own.length) return { entity: own[0] };
	if (p.component !== 'value') return undefined;
	for (const d of all) {
		if (d.id === device.id) continue;
		const e = presetFields(d, p)[0];
		if (e) return { device: d.id, entity: e };
	}
	return undefined;
}

/** The presses of a tap input that reports single / double / triple. */
export const TAPS = ['single', 'double', 'triple'];
export const tapsOf = (e: Entity) => TAPS.filter((a) => e.actions?.includes(a));

/** The size a new component starts with. */
export const startSize = (component: CardComponentType, style?: CardStyle) => (component === 'value' && style ? STYLES[style] : COMPONENTS[component]);

/** The colours a component or a rule can take, as tailwind classes (written out so they are not purged). */
export const COLORS: Record<CardColor, { text: string; tint: string; dot: string; fill: string }> = {
	primary: { text: 'text-primary', tint: 'bg-primary/20 text-primary', dot: 'bg-primary', fill: 'bg-primary/50' },
	secondary: { text: 'text-secondary', tint: 'bg-secondary/20 text-secondary', dot: 'bg-secondary', fill: 'bg-secondary/50' },
	accent: { text: 'text-accent', tint: 'bg-accent/20 text-accent', dot: 'bg-accent', fill: 'bg-accent/50' },
	success: { text: 'text-success', tint: 'bg-success/20 text-success', dot: 'bg-success', fill: 'bg-success/50' },
	warning: { text: 'text-warning', tint: 'bg-warning/20 text-warning', dot: 'bg-warning', fill: 'bg-warning/50' },
	error: { text: 'text-error', tint: 'bg-error/20 text-error', dot: 'bg-error', fill: 'bg-error/50' },
	info: { text: 'text-info', tint: 'bg-info/20 text-info', dot: 'bg-info', fill: 'bg-info/50' },
	neutral: { text: 'text-base-content', tint: 'bg-base-content/10', dot: 'bg-base-content/50', fill: 'bg-base-content/30' }
};
/** Icons a rule can show (backend CARD_ICONS). */
export const ICONS = ['bulb', 'plug', 'thermo', 'motion', 'door', 'gauge', 'star', 'eye', 'eyeoff', 'check', 'close', 'battery', 'wifi', 'power', 'clock', 'bell', 'bolt', 'home', 'pause'];

const overlap = (a: CardSlot, b: CardSlot) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

/** Whether a slot sits inside the card and clear of the others (`ignore` = the slot's own index). */
export function placeable(design: CardDesign, s: CardSlot, ignore = -1): boolean {
	const { cols, rows } = grid(design);
	if (s.x < 0 || s.y < 0 || s.w < 1 || s.h < 1 || s.x + s.w > cols || s.y + s.h > rows) return false;
	return design.slots.every((o, i) => i === ignore || !overlap(s, o));
}

/** The first free place (top-left first) for a w x h component, or null. */
export function freeSpot(design: CardDesign, w: number, h: number): { x: number; y: number } | null {
	const { cols, rows } = grid(design);
	for (let y = 0; y + h <= rows; y++) for (let x = 0; x + w <= cols; x++) if (placeable(design, { x, y, w, h } as CardSlot)) return { x, y };
	return null;
}

/** How small the card can get: no component may stick out. */
export function minSize(design: CardDesign): { w: number; h: number } {
	const right = Math.max(0, ...design.slots.map((s) => s.x + s.w));
	const bottom = Math.max(0, ...design.slots.map((s) => s.y + s.h));
	return { w: Math.max(1, Math.ceil(right / PER_COL)), h: Math.max(1, Math.ceil(bottom / PER_ROW)) };
}

/** What a device's card looks like when nobody designed it: the same slots and components, so the designer always
 * opens on what is on the card now. (A remote's buttons have their own look that is not made of components yet:
 * null.) */
export function defaultDesign(device: Device): CardDesign | null {
	const slots: CardSlot[] = [];
	const add = (component: CardComponentType, key: string | undefined, w: number, style?: CardStyle) => {
		if (!key) return;
		const x = slots.reduce((m, s) => Math.max(m, s.x + s.w), 0);
		slots.push({ x, y: 0, w, h: 2, component, key, ...(style ? { style } : {}) });
	};
	switch (deviceKind(device)) {
		case 'light': {
			const light = device.entities.find((e) => e.kind === 'light');
			add('switch', light?.key, 1);
			if (light && light.brightness !== null && light.brightness !== undefined) add('slider', light.key, 3);
			else add('value', light?.key, 3, 'chip'); // not dimmable: a bar that says On or Off
			break;
		}
		case 'switch': {
			const sw = device.entities.find((e) => e.kind === 'switch' || e.kind === 'fan');
			add('switch', sw?.key, 1);
			add('value', device.entities.find(isPower)?.key ?? sw?.key, 3, 'chip'); // the power it draws, else On or Off
			break;
		}
		case 'thermostat':
			add('dial', device.entities.find((e) => e.kind === 'climate')?.key, 4);
			break;
		case 'climate':
			add('value', device.entities.find(isTemperature)?.key, 2, 'text-l');
			add('value', device.entities.find(isHumidity)?.key, 2, 'text-l');
			break;
		case 'motion':
			add('value', presenceEntity(device)?.key, 4, 'chip');
			break;
		case 'contact':
			add('value', contactEntity(device)?.key, 4, 'chip');
			break;
		case 'button': {
			// A remote, laid out like its card always was: a Press button for an input you tap once, twice or three times;
			// a button for each press of an input that reports several (on, up, down, off); a knob for a brighter and
			// dimmer pair with its other buttons beside it; else a button for each button.
			const buttons = device.entities.filter((e) => e.kind === 'button').sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
			if (!buttons.length) return null;
			type Part = { key: string; component?: CardComponentType; label?: string; action?: string; wide?: boolean };
			const rows: Part[][] = [];
			const only = buttons[0];
			if (buttons.length === 1 && tapsOf(only).length > 1) rows.push([{ key: only.key, label: 'Press', wide: true }]);
			else if (buttons.length === 1 && (only.actions?.length ?? 0) > 1 && !only.actions!.some((a) => /multi_press|long_press/.test(a)))
				rows.push(only.actions!.filter((a) => !/release|hold/.test(a)).map((a) => ({ key: only.key, action: a, label: a.replace(/_press$/, '').replaceAll('_', ' ') })));
			else if (buttons.length === 1) rows.push([{ key: only.key, label: 'Press', wide: true }]);
			else if (buttons.some((e) => e.role === 'increase') && buttons.some((e) => e.role === 'decrease')) {
				for (const g of [...new Set(buttons.map((e) => e.group ?? null))]) {
					const mine = buttons.filter((e) => (e.group ?? null) === g);
					const up = mine.find((e) => e.role === 'increase');
					const others = mine.filter((e) => !e.role);
					const row: Part[] = [];
					if (up && mine.some((e) => e.role === 'decrease')) row.push({ key: up.key, component: 'knob', wide: !others.length });
					for (const e of others) row.push({ key: e.key, label: e.name });
					rows.push(row);
				}
			} else rows.push(buttons.map((e) => ({ key: e.key, label: e.name.replace(/^Button\s*/i, '') || e.name })));
			// the card's width for each row: a knob gets half of it (all of it alone), the rest share what is left
			rows.forEach((row, r) => {
				const knobs = row.filter((p) => p.component === 'knob').length;
				const used = row.reduce((n, p) => n + (p.component === 'knob' ? (p.wide ? PER_COL : 2) : p.wide ? PER_COL : 0), 0);
				const rest = row.filter((p) => p.component !== 'knob' && !p.wide);
				const each = rest.length ? Math.max(1, Math.floor((PER_COL - used) / rest.length)) : 1;
				let x = 0;
				for (const p of row) {
					const w = p.component === 'knob' ? (p.wide ? PER_COL : 2) : p.wide ? PER_COL : each;
					const { wide, ...slot } = p;
					slots.push({ x, y: r * 2, w, h: 2, ...slot, component: slot.component ?? 'button' } as CardSlot);
					x += w;
				}
				void knobs;
			});
			return { w: 1, h: Math.min(MAX_H, rows.length), slots };
		}
		case 'generic':
			for (const e of device.entities.filter((e) => e.kind !== 'button').slice(0, 2)) add('value', e.key, 2); // style left out: it picks one that suits the field
			break;
		default:
			break;
	}
	return slots.length ? { w: 1, h: 1, slots } : null;
}
