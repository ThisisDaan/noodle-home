import type { Device, Entity } from '../api.ts';
import { contactEntity, deviceKind, isHumidity, isPower, isTemperature, presenceEntity } from './kinds.ts';

/** How a device's card is designed: a size (a grid of slots) and components placed in it. Stored in the dashboard
 * layout (backend main.py CARD_SIZES / CARD_COMPONENTS must say the same). A device without a design keeps its
 * own look (DeviceFace). */
export type CardSize = 'small' | 'wide' | 'large';
export type CardComponentType = 'switch' | 'value' | 'dial' | 'slider' | 'graph';
export type CardSlot = { at: number; component: CardComponentType; key: string; label?: string };
export type CardDesign = { size: CardSize; slots: CardSlot[] };

/** cols x rows of slots. Small is today's tile; wide takes two tiles side by side; large two by two. */
export const SIZES: Record<CardSize, { cols: number; rows: number; label: string; hint: string }> = {
	small: { cols: 2, rows: 1, label: 'Small', hint: '2 slots' },
	wide: { cols: 4, rows: 1, label: 'Wide', hint: '4 slots' },
	large: { cols: 4, rows: 3, label: 'Large', hint: '12 slots' }
};

/** A component fills w x h slots. */
export const COMPONENTS: Record<CardComponentType, { w: number; h: number; label: string; hint: string }> = {
	switch: { w: 1, h: 1, label: 'Switch', hint: 'Tap to turn on or off' },
	value: { w: 1, h: 1, label: 'Value', hint: 'Shows a reading or text' },
	dial: { w: 2, h: 1, label: 'Dial', hint: 'Plus and minus buttons for a number' },
	slider: { w: 1, h: 1, label: 'Slider', hint: 'Drag to set a number or a brightness' },
	graph: { w: 2, h: 2, label: 'Graph', hint: 'The last hours of a reading' }
};

export const slotCount = (size: CardSize) => SIZES[size].cols * SIZES[size].rows;

/** The widths of a card's columns: a round power button stays as wide as it is, a column nothing is in gives its
 * room to the others, the rest share what is left. */
export function columns(design: CardDesign, labelled: boolean): string {
	const { cols } = SIZES[design.size];
	return Array.from({ length: cols }, (_, x) => {
		const here = design.slots.filter((s) => {
			const c = cells(design.size, s.at, s.component);
			return c?.some((i) => i % cols === x);
		});
		if (!here.length) return '0fr';
		return here.every((s) => s.component === 'switch' && !s.label && !labelled) ? '3rem' : 'minmax(0, 1fr)';
	}).join(' ');
}

/** The slot numbers a component at `at` covers, or null when it would stick out of the card. */
export function cells(size: CardSize, at: number, component: CardComponentType): number[] | null {
	const { cols, rows } = SIZES[size];
	const { w, h } = COMPONENTS[component];
	const x = at % cols, y = Math.floor(at / cols);
	if (at < 0 || x + w > cols || y + h > rows) return null;
	return Array.from({ length: h }, (_, j) => Array.from({ length: w }, (_, i) => (y + j) * cols + x + i)).flat();
}

/** Whether a component fits at a slot without covering another one (`ignore` = the slot being edited). */
export function fits(design: CardDesign, at: number, component: CardComponentType, ignore = -1): boolean {
	const mine = cells(design.size, at, component);
	if (!mine) return false;
	return design.slots.every((s, i) => i === ignore || !cells(design.size, s.at, s.component)?.some((c) => mine.includes(c)));
}

/** Which fields of a device a component can show or control. */
export function compatible(component: CardComponentType, e: Entity): boolean {
	switch (component) {
		case 'switch': return e.kind === 'switch' || e.kind === 'light' || e.kind === 'fan';
		case 'value': return e.kind !== 'button';
		case 'dial': return e.kind === 'number' || e.kind === 'climate';
		case 'slider': return e.kind === 'number' || (e.kind === 'light' && e.brightness !== null);
		case 'graph': return (e.kind === 'sensor' || e.kind === 'number') && typeof e.state === 'number';
	}
}

/** Tailwind classes that give a designed card its place in the tile grid (a grid item). */
export function span(size: CardSize | undefined): string {
	return size === 'wide' ? 'sm:col-span-2' : size === 'large' ? 'sm:col-span-2 sm:row-span-2' : '';
}

/** What a device's card looks like when nobody designed it: the same slots and components, so the designer always
 * opens on what is on the card now. (A remote's buttons have their own look that is not made of components yet:
 * null.) */
export function defaultDesign(device: Device): CardDesign | null {
	const slots: CardSlot[] = [];
	const add = (component: CardComponentType, key: string | undefined) => {
		if (key) slots.push({ at: slots.length ? slots[slots.length - 1].at + COMPONENTS[slots[slots.length - 1].component].w : 0, component, key });
	};
	switch (deviceKind(device)) {
		case 'light': {
			const light = device.entities.find((e) => e.kind === 'light');
			add('switch', light?.key);
			if (light && light.brightness !== null && light.brightness !== undefined) add('slider', light.key);
			else add('value', light?.key); // not dimmable: a bar that says On or Off
			break;
		}
		case 'switch':
			const sw = device.entities.find((e) => e.kind === 'switch' || e.kind === 'fan');
			add('switch', sw?.key);
			add('value', device.entities.find(isPower)?.key ?? sw?.key); // the power it draws, else On or Off
			break;
		case 'thermostat':
			add('dial', device.entities.find((e) => e.kind === 'climate')?.key);
			break;
		case 'climate':
			add('value', device.entities.find(isTemperature)?.key);
			add('value', device.entities.find(isHumidity)?.key);
			break;
		case 'motion':
			add('value', presenceEntity(device)?.key);
			break;
		case 'contact':
			add('value', contactEntity(device)?.key);
			break;
		case 'generic':
			for (const e of device.entities.filter((e) => e.kind !== 'button').slice(0, 2)) add('value', e.key);
			break;
		default:
			break;
	}
	return slots.length ? { size: 'small', slots } : null;
}
