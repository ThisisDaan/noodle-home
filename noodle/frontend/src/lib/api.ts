export type Entity = {
	key: string;
	kind: 'light' | 'switch' | 'binary_sensor' | 'sensor' | 'button' | 'number';
	name: string;
	state: boolean | number | string | null;
	brightness: number | null;
	unit: string | null;
	device_class: string | null;
	/** Buttons: the presses this button can send. */
	actions?: string[] | null;
	/** Inputs that belong together, e.g. one profile of a remote. */
	group?: string | null;
};

export type Device = {
	id: string;
	source: 'zigbee' | 'matter' | 'ble' | 'thermostat' | 'hue' | 'group';
	name: string;
	model: string | null;
	manufacturer: string | null;
	available: boolean;
	battery: number | null;
	area: string | null;
	last_seen: number | null;
	presence_minutes: number | null;
	entities: Entity[];
};

export class ApiError extends Error {
	constructor(
		public status: number,
		message: string
	) {
		super(message);
	}
}

export async function api<T = unknown>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
	const res = await fetch(`/api${path}`, {
		method: init.method ?? (init.body === undefined ? 'GET' : 'POST'),
		headers: init.body === undefined ? undefined : { 'Content-Type': 'application/json' },
		body: init.body === undefined ? undefined : JSON.stringify(init.body)
	});
	if (!res.ok) {
		let detail = res.statusText;
		try {
			const data = await res.json();
			detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
		} catch {
			/* not JSON */
		}
		throw new ApiError(res.status, detail);
	}
	return res.json() as Promise<T>;
}

export const command = (device: Device, entity: Entity, body: { on?: boolean; brightness?: number; toggle?: boolean; value?: number }) =>
	api(`/devices/${encodeURIComponent(device.id)}/entities/${encodeURIComponent(entity.key)}`, { body });

export const controllable = (e: Entity) => e.kind === 'light' || e.kind === 'switch' || e.kind === 'number';

export function formatState(e: Entity): string {
	if (e.state === null || e.state === undefined) return '–';
	if (e.kind === 'binary_sensor') {
		if (e.device_class === 'occupancy') return e.state ? 'Motion' : 'Clear';
		if (e.device_class === 'presence') return e.state ? 'Someone there' : 'Empty';
		if (e.device_class === 'contact') return e.state ? 'Open' : 'Closed';
		if (e.device_class === 'heat') return e.state ? 'Heating' : 'Idle';
		return e.state ? 'On' : 'Off';
	}
	if (e.kind === 'button') return String(e.state).replaceAll('_', ' ');
	if (typeof e.state === 'boolean') return e.state ? 'On' : 'Off';
	return `${e.state}${e.unit ? ' ' + e.unit : ''}`;
}

export function ago(ts: number | null): string {
	if (!ts) return 'never';
	const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
	if (s < 60) return `${s}s ago`;
	if (s < 3600) return `${Math.round(s / 60)}m ago`;
	if (s < 86400) return `${Math.round(s / 3600)}h ago`;
	return `${Math.round(s / 86400)}d ago`;
}

/** Icon name that best describes a device. */
export function iconFor(d: Device): string {
	const kinds = d.entities.map((e) => e.kind);
	if (kinds.includes('light')) return 'bulb';
	if (d.entities.some((e) => e.key === 'heat' || e.device_class === 'heat' || e.device_class === 'temperature')) return 'thermo';
	if (kinds.includes('switch')) return 'plug';
	if (d.entities.some((e) => e.device_class === 'occupancy')) return 'motion';
	if (d.entities.some((e) => e.device_class === 'contact')) return 'door';
	if (kinds.includes('sensor')) return 'gauge';
	return 'circle';
}

/** Whether a device counts as "on" (any light or switch that is on). */
export const isOn = (d: Device) => d.available && d.entities.some((e) => (e.kind === 'light' || e.kind === 'switch') && e.state === true);

/** A short, readable line summarising a device for its tile. */
export function headline(d: Device): string {
	if (!d.available) return 'Offline';
	const light = d.entities.find((e) => e.kind === 'light');
	if (light) return light.state ? (light.brightness !== null ? `On · ${light.brightness}%` : 'On') : 'Off';
	const sw = d.entities.find((e) => e.kind === 'switch');
	if (sw) return sw.state ? 'On' : 'Off';
	const shown = d.entities.filter((e) => e.kind !== 'button' && e.state !== null && e.state !== undefined);
	return shown.slice(0, 2).map(formatState).join(' · ') || 'No data';
}
