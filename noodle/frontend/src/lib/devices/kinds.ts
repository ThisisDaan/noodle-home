import type { Device, Entity } from '../api.ts';

/** How a device is shown: the face it gets on its tile and at the top of its sheet (see DeviceFace.svelte). */
export type DeviceKind = 'light' | 'button' | 'motion' | 'climate' | 'generic';

export const isMotion = (e: Entity) => e.kind === 'binary_sensor' && (e.device_class === 'occupancy' || e.device_class === 'presence');
export const isTemperature = (e: Entity) => e.kind === 'sensor' && e.device_class === 'temperature';
export const isHumidity = (e: Entity) => e.kind === 'sensor' && e.device_class === 'humidity';

export function deviceKind(d: Device): DeviceKind {
	if (d.entities.some((e) => e.kind === 'light')) return 'light';
	if (d.entities.some((e) => e.kind === 'switch' || e.kind === 'fan' || e.kind === 'cover' || e.kind === 'lock' || e.kind === 'climate')) return 'generic';
	if (d.entities.some((e) => e.kind === 'button')) return 'button';
	if (d.entities.some(isMotion)) return 'motion';
	if (d.entities.some((e) => isTemperature(e) || isHumidity(e))) return 'climate';
	return 'generic';
}

/** The entities a device's face already shows, so the sheet does not list them a second time. Battery, the
 * device's own temperature and the like are not among them: they stay in the properties. */
export function faceEntities(d: Device): Entity[] {
	switch (deviceKind(d)) {
		case 'climate': return d.entities.filter((e) => isTemperature(e) || isHumidity(e));
		case 'motion': return d.entities.filter(isMotion);
		case 'button': return d.entities.filter((e) => e.kind === 'button');
		default: return [];
	}
}
