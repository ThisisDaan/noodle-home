import type { Device } from '../api.ts';

type Entity = Device['entities'][number];
export type Pick = { id: string; label: string; match: (e: Entity) => boolean };
export type Chosen = { device: Device; entity: Entity };
export type Template = {
	id: string;
	title: string;
	blurb: string;
	picks: Pick[];
	build: (p: Record<string, Chosen>) => { name: string; graph: { nodes: any[]; edges: any[] } };
};

const light: Pick['match'] = (e) => e.kind === 'light' || e.kind === 'switch';
const colX = (c: number) => c * 376;

const node = (id: string, type: string, data: Record<string, unknown>, col: number, row = 0) => ({
	id, type, data, position: { x: colX(col), y: row * 140 }
});
const edge = (source: string, sourceHandle: string, target: string, targetHandle?: string) => ({
	id: `${source}-${sourceHandle}-${target}` + (targetHandle ? `-${targetHandle}` : ''),
	source, sourceHandle, target, ...(targetHandle ? { targetHandle } : {})
});
const control = (id: string, p: Chosen, action: string, col: number, row = 0) =>
	node(id, 'action.device', { device_id: p.device.id, key: p.entity.key, inputs: [action], brightness: 50, step: 5, min: 1 }, col, row);

export const TEMPLATES: Template[] = [
	{
		id: 'motion',
		title: 'Motion light',
		blurb: 'Light on when there is motion in the dark, off 5 minutes after the last movement.',
		picks: [
			{ id: 'sensor', label: 'Motion sensor', match: (e) => e.kind === 'binary_sensor' && (e.device_class === 'occupancy' || e.device_class === 'motion' || e.device_class === 'presence') },
			{ id: 'light', label: 'Light', match: light }
		],
		build: ({ sensor, light }) => ({
			name: `${sensor.device.name} → ${light.device.name}`,
			graph: {
				nodes: [
					node('motion', 'trigger.state', { device_id: sensor.device.id, outputs: [`${sensor.entity.key}:on`, `${sensor.entity.key}:off`] }, 0),
					node('dark', 'cond.dark', {}, 1, 0),
					control('on', light, 'on', 2, 0),
					node('timer', 'action.timer', { minutes: 5, restart: true }, 1, 1),
					control('off', light, 'off', 2, 1)
				],
				edges: [
					edge('motion', `${sensor.entity.key}:on`, 'dark'),
					edge('dark', 'yes', 'on', 'on'),
					edge('motion', `${sensor.entity.key}:on`, 'timer', 'stop'),
					edge('motion', `${sensor.entity.key}:off`, 'timer', 'start'),
					edge('timer', 'out', 'off', 'off')
				]
			}
		})
	},
	{
		id: 'button',
		title: 'Button toggles a light',
		blurb: 'Press a button to switch a light on or off.',
		picks: [
			{ id: 'button', label: 'Button', match: (e) => e.kind === 'button' },
			{ id: 'light', label: 'Light', match: light }
		],
		build: ({ button, light }) => {
			const press = `${button.entity.key}:${(button.entity.actions ?? []).includes('single') ? 'single' : ((button.entity.actions ?? [])[0] ?? '*')}`;
			return {
				name: `${button.device.name} → ${light.device.name}`,
				graph: {
					nodes: [node('button', 'trigger.event', { device_id: button.device.id, outputs: [press] }, 0), control('toggle', light, 'toggle', 1)],
					edges: [edge('button', press, 'toggle', 'toggle')]
				}
			};
		}
	},
	{
		id: 'sunset',
		title: 'Lights on at sunset',
		blurb: 'Switch a light on when the sun goes down.',
		picks: [{ id: 'light', label: 'Light', match: light }],
		build: ({ light }) => ({
			name: `Sunset → ${light.device.name}`,
			graph: {
				nodes: [node('sun', 'trigger.sun', { event: 'sunset', offset: 0 }, 0), control('on', light, 'on', 1)],
				edges: [edge('sun', 'out', 'on', 'on')]
			}
		})
	},
	{
		id: 'bedtime',
		title: 'Switch off at bedtime',
		blurb: 'Turn a light off every night at 23:00.',
		picks: [{ id: 'light', label: 'Light', match: light }],
		build: ({ light }) => ({
			name: `Bedtime → ${light.device.name}`,
			graph: {
				nodes: [node('time', 'trigger.time', { at: '23:00' }, 0), control('off', light, 'off', 1)],
				edges: [edge('time', 'out', 'off', 'off')]
			}
		})
	},
	{
		id: 'open',
		title: 'Tell me when a door opens',
		blurb: 'Phone notification when a door or window opens (at most once per 5 minutes).',
		picks: [{ id: 'door', label: 'Door or window sensor', match: (e) => e.kind === 'binary_sensor' && (e.device_class === 'contact' || e.device_class === 'door' || e.device_class === 'window') }],
		build: ({ door }) => ({
			name: `${door.device.name} opens`,
			graph: {
				nodes: [
					node('door', 'trigger.state', { device_id: door.device.id, outputs: [`${door.entity.key}:on`] }, 0),
					node('once', 'action.throttle', { minutes: 5 }, 1),
					node('tell', 'action.notify', { title: 'Noodle', message: `${door.device.name} opened`, priority: 'default', buttons: [] }, 2)
				],
				edges: [edge('door', `${door.entity.key}:on`, 'once'), edge('once', 'out', 'tell')]
			}
		})
	}
];

/** The device (and entity) each pick of a template can use right now. */
export function candidates(pick: Pick, devices: Device[]): Chosen[] {
	return devices.flatMap((device) => device.entities.filter(pick.match).slice(0, 1).map((entity) => ({ device, entity })));
}
