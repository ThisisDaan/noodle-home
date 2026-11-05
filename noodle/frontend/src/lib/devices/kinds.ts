import type { Device, Entity } from '../api.ts';

/** How a device is shown: the face it gets on its card and, for some, at the top of its sheet (DeviceFace.svelte). */
export type DeviceKind = 'light' | 'switch' | 'button' | 'motion' | 'contact' | 'climate' | 'generic';

export const isMotion = (e: Entity) => e.kind === 'binary_sensor' && (e.device_class === 'occupancy' || e.device_class === 'presence');
/** What a presence-capable sensor shows: its "presence" entity (motion that holds for a few minutes) when it has
 * one, else the raw motion/occupancy entity. */
export const presenceEntity = (d: Device): Entity | undefined =>
	d.entities.find((e) => isMotion(e) && e.device_class === 'presence') ?? d.entities.find(isMotion);
export const isContact = (e: Entity) => e.kind === 'binary_sensor' && ['contact', 'door', 'window', 'opening', 'garage_door'].includes(e.device_class ?? '');
/** What a door sensor shows: whether it is open. */
export const contactEntity = (d: Device): Entity | undefined => d.entities.find(isContact);
export const isTemperature = (e: Entity) => e.kind === 'sensor' && e.device_class === 'temperature';
export const isHumidity = (e: Entity) => e.kind === 'sensor' && e.device_class === 'humidity';
export const isPower = (e: Entity) => e.kind === 'sensor' && e.device_class === 'power';

export function deviceKind(d: Device): DeviceKind {
	const has = (...kinds: Entity['kind'][]) => d.entities.some((e) => kinds.includes(e.kind));
	if (has('light')) return 'light';
	if (has('cover', 'lock', 'climate')) return 'generic';
	if (has('switch', 'fan')) return 'switch';
	if (has('button')) return 'button';
	if (d.entities.some(isMotion)) return 'motion';
	if (d.entities.some(isContact)) return 'contact'; // a door sensor with a temperature is still a door sensor
	if (d.entities.some((e) => isTemperature(e) || isHumidity(e))) return 'climate';
	return 'generic';
}

/** Someone is there now: the card lights up like a light that is on. */
export const motionActive = (d: Device) => d.available && presenceEntity(d)?.state === true;

/** The entities a device's face at the top of the sheet already shows, so the lists below do not repeat them.
 * Battery, the device's own temperature and the rest stay in the properties. */
export function faceEntities(d: Device): Entity[] {
	switch (deviceKind(d)) {
		case 'climate': return d.entities.filter((e) => isTemperature(e) || isHumidity(e));
		case 'motion': return d.entities.filter(isMotion);
		case 'contact': return d.entities.filter(isContact);
		default: return [];
	}
}

/** Kinds that get a large face at the top of the device sheet. */
export const sheetFace = (d: Device) => ['climate', 'motion', 'contact'].includes(deviceKind(d));
