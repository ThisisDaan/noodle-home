import type { Device, Entity } from '../api.ts';
import { contactEntity, deviceKind, isContact, isHumidity, isMotion, isPower, isTemperature, presenceEntity } from './kinds.ts';

/** How a device's card is designed: a size in dashboard cells (w x h) and components placed anywhere on the card's
 * fine grid, each with its own position, size and display style. Stored in the dashboard layout (backend main.py
 * CARD_* must say the same). A remote's buttons have their own look (DeviceFace) and no design. */
export type CardComponentType = 'switch' | 'value' | 'dial' | 'slider' | 'text';
export type CardStyle = 'text-s' | 'text-m' | 'text-l' | 'chip' | 'icon' | 'gauge' | 'bar' | 'line' | 'bars' | 'spark';
export type CardColor = 'primary' | 'secondary' | 'accent' | 'success' | 'warning' | 'error' | 'info' | 'neutral';
export type RuleOp = 'is' | 'not' | 'above' | 'below' | 'between';
/** When `field` (default: the component's own) <op> value, then the component shows this instead; first match wins. */
export type CardRule = { field?: string; op: RuleOp; value: string | number; value2?: number; then: { text?: string; color?: CardColor; icon?: string; hide?: boolean } };
export type CardSlot = {
	x: number; y: number; w: number; h: number; component: CardComponentType;
	/** the device's field ('' for a label) */
	key: string;
	style?: CardStyle; label?: string; hours?: number;
	/** the text, with {tokens} (see cardText.ts); without one the component shows its field as it always did */
	template?: string;
	/** number format */
	decimals?: number; unit?: string; thousands?: boolean;
	/** text style */
	bold?: boolean; align?: 'left' | 'center' | 'right'; color?: CardColor;
	rules?: CardRule[];
};
export type CardDesign = { w: number; h: number; slots: CardSlot[] };

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
	text: { label: 'Label', hint: 'Text you write, with values from the device in it', w: 3, h: 1 }
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

/** The styles a field can be shown in: a number as text, gauge, bar or graph; anything else as text, a status bar or an icon. */
export function stylesFor(e: Entity): CardStyle[] {
	const numeric = typeof e.state === 'number';
	return (Object.keys(STYLES) as CardStyle[]).filter((s) => STYLES[s].plain || (numeric ? STYLES[s].numeric : !STYLES[s].numeric));
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
	{ id: 'switch', label: 'Switch', component: 'switch' },
	{ id: 'slider', label: 'Slider', component: 'slider' },
	{ id: 'dial', label: 'Dial', component: 'dial' }
];
/** Whether a preset has a field to work with on this device (a graph needs a number, a status bar does not). */
export function presetFields(device: Device, p: (typeof PRESETS)[number]): Entity[] {
	if (p.component === 'text') return [];
	return device.entities.filter((e) => compatible(p.component, e) && (!p.style || stylesFor(e).includes(p.style)));
}

/** The size a new component starts with. */
export const startSize = (component: CardComponentType, style?: CardStyle) => (component === 'value' && style ? STYLES[style] : COMPONENTS[component]);

/** The colours a component or a rule can take, as tailwind classes (written out so they are not purged). */
export const COLORS: Record<CardColor, { text: string; tint: string; dot: string }> = {
	primary: { text: 'text-primary', tint: 'bg-primary/20 text-primary', dot: 'bg-primary' },
	secondary: { text: 'text-secondary', tint: 'bg-secondary/20 text-secondary', dot: 'bg-secondary' },
	accent: { text: 'text-accent', tint: 'bg-accent/20 text-accent', dot: 'bg-accent' },
	success: { text: 'text-success', tint: 'bg-success/20 text-success', dot: 'bg-success' },
	warning: { text: 'text-warning', tint: 'bg-warning/20 text-warning', dot: 'bg-warning' },
	error: { text: 'text-error', tint: 'bg-error/20 text-error', dot: 'bg-error' },
	info: { text: 'text-info', tint: 'bg-info/20 text-info', dot: 'bg-info' },
	neutral: { text: 'text-base-content', tint: 'bg-base-content/10', dot: 'bg-base-content/50' }
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
		case 'generic':
			for (const e of device.entities.filter((e) => e.kind !== 'button').slice(0, 2)) add('value', e.key, 2); // style left out: it picks one that suits the field
			break;
		default:
			break;
	}
	return slots.length ? { w: 1, h: 1, slots } : null;
}
