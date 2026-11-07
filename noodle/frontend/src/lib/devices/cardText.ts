import { formatState, type Device, type Entity } from '../api.ts';
import { agoText } from './clock.svelte.ts';
import type { CardColor, CardRule, CardSlot } from './cardDesign.ts';

/** What a component shows when its text, number format and rules are applied. Pure: the card (and the designer's
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

/** The tokens a template can use, for the designer's picker. ({field:<key>} ones are added per field of the device.) */
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

/** Fill the {tokens} of a template: {value} {name} {unit} {device} {changed[:ago|clock|datetime]} {seen[:...]} and
 * {field:<key>} for another field of the device. Anything it does not know stays as typed. */
export function fillTemplate(template: string, device: Device, e: Entity | undefined, slot: CardSlot, now: number): string {
	return template.replace(/\{([a-z]+)(?::([^}]*))?\}/g, (whole, name: string, arg?: string) => {
		switch (name) {
			case 'value': return valueText(e, { ...slot, unit: '' }).trim();
			case 'name': return slot.label || e?.name || '';
			case 'unit': return unitOf(e, slot);
			case 'device': return device.name;
			case 'changed': return timeText(e?.changed, arg ?? 'ago', now);
			case 'seen': return timeText(device.last_seen, arg ?? 'ago', now);
			case 'field': {
				const f = device.entities.find((x) => x.key === arg);
				return f ? valueText(f, f.key === e?.key ? slot : {}) : whole;
			}
			default: return whole;
		}
	});
}

const word = (v: unknown) => String(v).trim().toLowerCase();
const YES = ['on', 'true', 'yes'];
const NO = ['off', 'false', 'no'];
/** On/off style values compare as words (a yes/no field is "on" or "off"); numbers compare as numbers. */
function same(state: Entity['state'], value: string | number): boolean {
	if (typeof state === 'boolean') return state ? YES.includes(word(value)) : NO.includes(word(value));
	if (typeof state === 'number') return Number(value) === state;
	return state !== null && word(state) === word(value);
}

/** Whether a rule's condition holds for the device now. A field that is gone or has no value matches nothing. */
export function ruleMatches(rule: CardRule, device: Device, slot: CardSlot): boolean {
	const e = device.entities.find((x) => x.key === (rule.field || slot.key));
	if (!e || e.state === null || e.state === undefined) return false;
	const n = typeof e.state === 'number' ? e.state : NaN;
	switch (rule.op) {
		case 'is': return same(e.state, rule.value);
		case 'not': return !same(e.state, rule.value);
		case 'above': return n > Number(rule.value);
		case 'below': return n < Number(rule.value);
		case 'between': return n >= Number(rule.value) && n <= Number(rule.value2 ?? NaN);
	}
}

export type Shown = {
	/** the text to show instead of the field's own; undefined: show the field as usual */
	text?: string;
	color?: CardColor;
	icon?: string;
	hide: boolean;
	/** which rule applied (its index), -1 for none */
	rule: number;
};

/** Apply the component's text and the first rule that matches. A rule's text replaces the component's own. */
export function resolve(slot: CardSlot, device: Device, now: number): Shown {
	const e = device.entities.find((x) => x.key === slot.key);
	const i = (slot.rules ?? []).findIndex((r) => ruleMatches(r, device, slot));
	const then = i >= 0 ? slot.rules![i].then : undefined;
	const source = then?.text ?? slot.template;
	return {
		text: source !== undefined ? fillTemplate(source, device, e, slot, now) : undefined,
		color: then?.color ?? slot.color,
		icon: then?.icon,
		hide: !!then?.hide,
		rule: i
	};
}
