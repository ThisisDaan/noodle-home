import type { Device } from '../api.ts';
import { activity } from './activity.svelte.ts';

export const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export type Category = 'trigger' | 'condition' | 'action';
export type NodeDef = {
	type: string;
	label: string;
	category: Category;
	defaults: Record<string, unknown>;
	/** Entity kinds the node's device picker offers (none = no picker). */
	kinds?: string[];
	/** Only entities of these device classes (e.g. temperature). */
	classes?: string[];
	/** Nodes an integration adds (see /api/flow/nodes): the form of their properties and their one-line summary. */
	fields?: NodeField[];
	summary?: string;
	/** False while the integration that adds the node is not added, or for a node kept only for old flows (Wait); it stays in DEFS so old flows still show it. */
	available?: boolean;
};
export type NodeField = {
	key: string;
	label: string;
	type: 'text' | 'textarea' | 'number' | 'select' | 'buttons';
	options: [string, string][];
	hint: string;
};
export type NodeSpec = NodeDef & { icon: string; plugin: string; summary: string; fields: NodeField[] };

/** Add the nodes integrations bring to the nodes above. */
export function registerNodes(specs: NodeSpec[]) {
	for (const s of specs) {
		const def: NodeDef = { type: s.type, label: s.label, category: s.category, defaults: s.defaults, fields: s.fields, summary: s.summary, available: s.available };
		const at = CATALOG.findIndex((d) => d.type === s.type);
		if (at >= 0) CATALOG[at] = def;
		else CATALOG.push(def);
		DEFS[s.type] = def;
		NODE_ICON[s.type] = s.icon;
	}
}

/** Can this node use this entity? */
export const accepts = (def: NodeDef | undefined, e: { kind: string; device_class?: string | null }) =>
	!!def?.kinds?.includes(e.kind) && (!def.classes || def.classes.includes(e.device_class ?? ''));

export const CATALOG: NodeDef[] = [
	{ type: 'trigger.state', label: 'Device changes', category: 'trigger', defaults: {}, kinds: ['light', 'switch', 'binary_sensor', 'sensor'] },
	{ type: 'trigger.event', label: 'Button pressed', category: 'trigger', defaults: { action: '' }, kinds: ['button'] },
	{ type: 'trigger.control', label: 'Card control', category: 'trigger', defaults: { control: '' } },
	{ type: 'trigger.thermostat', label: 'Thermostat', category: 'trigger', defaults: { target: 20, margin: 0.5 }, kinds: ['sensor'], classes: ['temperature'] },
	{ type: 'trigger.time', label: 'Time of day', category: 'trigger', defaults: { at: '07:00' } },
	{ type: 'trigger.interval', label: 'Every…', category: 'trigger', defaults: { seconds: 60 } },
	{ type: 'trigger.webhook', label: 'Phone notification button', category: 'trigger', defaults: { name: 'my_hook' } },
	{ type: 'trigger.sun', label: 'Sunrise / sunset', category: 'trigger', defaults: { event: 'sunset', offset: 0 } },
	{ type: 'trigger.manual', label: 'Run button', category: 'trigger', defaults: {} },
	{ type: 'cond.day', label: 'Day of the week', category: 'condition', defaults: { days: [0, 1, 2, 3, 4] } },
	{ type: 'cond.dark', label: 'Is it dark?', category: 'condition', defaults: {} },
	{ type: 'cond.state', label: 'Check state', category: 'condition', defaults: {}, kinds: ['light', 'switch', 'binary_sensor', 'sensor'] },
	{ type: 'cond.for', label: 'In state for…', category: 'condition', defaults: { state: 'on', minutes: 10 }, kinds: ['light', 'switch', 'binary_sensor', 'sensor'] },
	{ type: 'cond.time', label: 'Between times', category: 'condition', defaults: { from: '22:00', to: '06:30' } },
	{ type: 'cond.control', label: 'Card control is…', category: 'condition', defaults: { control: '', value: 'on' } },
	{ type: 'cond.var', label: 'Check variable', category: 'condition', defaults: { name: 'status', op: 'eq', value: '' } },
	{ type: 'action.device', label: 'Control device', category: 'action', defaults: { inputs: ['toggle'], brightness: 50, step: 5, min: 1, loop_levels: [25, 50, 75, 100], loop_seconds: 1, loop_max_seconds: 60 }, kinds: ['light', 'switch', 'fan', 'cover', 'lock', 'climate'] },
	{ type: 'action.throttle', label: 'Only once per…', category: 'action', defaults: { minutes: 5 } },
	{ type: 'action.http', label: 'Call web address', category: 'action', defaults: { url: 'https://', method: 'GET', body: '' } },
	{ type: 'action.flow', label: 'Run another flow', category: 'action', defaults: { flow_id: '' } },
	{ type: 'action.cycle', label: 'Cycle', category: 'action', defaults: { inputs: ['next', 'back', 'loop'], steps: [{ brightness: 25 }, { brightness: 50 }, { brightness: 75 }, { brightness: 100 }] } },
	{ type: 'action.repeat', label: 'Repeat', category: 'action', defaults: { seconds: 0.5, max_seconds: 30 } },
	{ type: 'action.delay', label: 'Wait', category: 'action', defaults: { seconds: 5 }, available: false }, // old flows only: use Timer
	{ type: 'action.timer', label: 'Timer', category: 'action', defaults: { minutes: 5, restart: true } },
	{ type: 'action.log', label: 'Log message', category: 'action', defaults: { message: 'Something happened' } },
	{ type: 'action.var', label: 'Set variable', category: 'action', defaults: { name: 'status', value: '' } }
];

export const DEFS: Record<string, NodeDef> = Object.fromEntries(CATALOG.map((d) => [d.type, d]));

/** Solid colour for stripes and dots; text stays neutral so it is always readable. */
export const CATEGORY_STYLE: Record<Category, string> = {
	trigger: 'bg-info',
	condition: 'bg-warning',
	action: 'bg-success'
};
/** Soft tinted icon badge for each category. */
export const CATEGORY_BADGE: Record<Category, string> = {
	trigger: 'bg-info/15 text-info',
	condition: 'bg-warning/20 text-warning',
	action: 'bg-success/15 text-success'
};
export const CATEGORY_NAME: Record<Category, string> = {
	trigger: 'When',
	condition: 'Only if',
	action: 'Then'
};
export const NODE_ICON: Record<string, string> = {
	'trigger.state': 'bolt',
	'trigger.event': 'circle',
	'trigger.thermostat': 'thermo',
	'trigger.control': 'dial',
	'trigger.time': 'clock',
	'trigger.interval': 'timer',
	'trigger.webhook': 'bell',
	'trigger.sun': 'clock',
	'trigger.manual': 'circle',
	'cond.day': 'clock',
	'cond.dark': 'branch',
	'action.throttle': 'pause',
	'action.http': 'bolt',
	'action.flow': 'branch',
	'cond.state': 'branch',
	'cond.for': 'timer',
	'cond.time': 'clock',
	'cond.var': 'variable',
	'cond.control': 'dial',
	'action.device': 'bulb',
	'action.cycle': 'branch',
	'action.repeat': 'timer',
	'action.delay': 'pause',
	'action.timer': 'timer',
	'action.log': 'note',
	'action.var': 'variable'
};

export type Output = { id: string; label: string; tone: 'yes' | 'no' | 'neutral'; group?: string };

/** What "Control device" can do; the ones ticked in its properties become its inputs. Brightness ones are lights only. */
export const DEVICE_ACTIONS = ['on', 'off', 'toggle', 'brightness', 'brighter', 'dimmer', 'loop_start', 'loop_stop', 'message', 'open', 'close', 'stop', 'lock', 'unlock'] as const;
export const DIM_ACTIONS = ['brightness', 'brighter', 'dimmer', 'loop_start', 'loop_stop'];
/** The actions that make sense for each kind of entity (see backend capabilities.py). No device picked yet: on / off. */
const ACTIONS_BY_KIND: Record<string, string[]> = {
	light: ['on', 'off', 'toggle', ...DIM_ACTIONS, 'message'],
	switch: ['on', 'off', 'toggle', 'message'],
	fan: ['on', 'off', 'toggle', 'message'],
	cover: ['open', 'close', 'stop', 'message'],
	lock: ['lock', 'unlock', 'message'],
	climate: ['message'],
	number: ['message']
};
export const actionsFor = (kind?: string): string[] => ACTIONS_BY_KIND[kind ?? ''] ?? ['on', 'off', 'toggle', 'message'];
export function deviceActionLabel(action: string, d: Record<string, any>): string {
	return {
		on: 'Turn on',
		off: 'Turn off',
		toggle: 'Toggle',
		brightness: `Set to ${d.brightness ?? 50}%`,
		brighter: `Brighter (+${d.step ?? 5}% per press)`,
		dimmer: `Dimmer (-${d.step ?? 5}% per press)`,
		loop_start: `Start brightness loop (${(d.loop_levels ?? [25, 50, 75, 100]).join(' → ')}%)`,
		loop_stop: 'Stop brightness loop',
		message: 'Message: brightness, on, toggle, color, position',
		open: 'Open',
		close: 'Close',
		stop: 'Stop',
		lock: 'Lock',
		unlock: 'Unlock'
	}[action] ?? action;
}

/** "Cycle" inputs: Next / Back stop at the ends, Loop goes forward and wraps around. */
export const CYCLE_INPUTS: Output[] = [
	{ id: 'next', label: 'Next', tone: 'yes' },
	{ id: 'back', label: 'Back', tone: 'no' },
	{ id: 'loop', label: 'Loop', tone: 'neutral' }
];

/** Named connection points on the left, for nodes that do different things per input (others have one). */
export function inputs(type: string, d: Record<string, any>): Output[] {
	if (type === 'action.timer') {
		return [
			{ id: 'start', label: 'Start', tone: 'yes' },
			{ id: 'stop', label: 'Stop', tone: 'no' }
		];
	}
	if (type === 'action.repeat') {
		return [
			{ id: 'start', label: 'Start', tone: 'yes' },
			{ id: 'stop', label: 'Stop', tone: 'no' }
		];
	}
	if (type === 'trigger.thermostat') {
		// Lets another trigger (e.g. someone arrives) make it look at the temperature right now.
		return [{ id: 'check', label: 'Check temperature now', tone: 'neutral' }];
	}
	if (type === 'action.cycle') {
		return CYCLE_INPUTS.filter((i) => (d.inputs ?? CYCLE_INPUTS.map((c) => c.id)).includes(i.id));
	}
	if (type === 'action.device') {
		const chosen: string[] = d.inputs?.length ? d.inputs : [d.command ?? 'toggle'];
		return DEVICE_ACTIONS.filter((a) => chosen.includes(a)).map((a) => ({
			id: a,
			label: deviceActionLabel(a, d),
			tone: a === 'off' || a === 'loop_stop' ? 'no' : a === 'on' || a === 'loop_start' ? 'yes' : 'neutral'
		}));
	}
	return [];
}

const CHANGE_WORDS: Record<string, [string, string]> = {
	occupancy: ['Motion detected', 'Motion stopped'],
	presence: ['Presence detected', 'Presence cleared'],
	contact: ['Opens', 'Closes'],
	heat: ['Starts heating', 'Stops heating']
};

/** Everything "Device changes" can react to on a device; the ones ticked in its properties become its outputs.
 * Ids are "<entity>:on" / "<entity>:off", or "<entity>:out" for a reading that changes. */
export function changeOptions(dev?: Device): Output[] {
	const usable = (dev?.entities ?? []).filter((e) => accepts(DEFS['trigger.state'], e) && e.device_class !== 'device_temperature');
	const named = usable.length > 1;
	return usable.flatMap((e): Output[] => {
		if (e.kind === 'sensor') return [{ id: `${e.key}:out`, label: `${e.name} changes`, tone: 'neutral' }];
		const words: [string, string] | undefined = CHANGE_WORDS[e.device_class ?? ''];
		const [on, off] = words ?? (e.kind === 'light' || e.kind === 'switch' ? ['Turns on', 'Turns off'] : ['Becomes on', 'Becomes off']);
		const prefix = named && !words ? `${e.name}: ` : '';
		return [
			{ id: `${e.key}:on`, label: prefix + on, tone: 'yes' },
			{ id: `${e.key}:off`, label: prefix + off, tone: 'no' }
		];
	});
}

/** What a new "Device changes" node starts with: both changes of the picked (or first) entity, e.g. motion detected / stopped. */
export function defaultChanges(dev?: Device, key?: string): string[] {
	const opts = changeOptions(dev);
	const first = key ?? opts[0]?.id.split(':')[0];
	const pick = opts.filter((o) => o.id.split(':')[0] === first);
	return (pick.length ? pick : opts.slice(0, 2)).map((o) => o.id);
}

const PRESS_WORDS: Record<string, string> = {
	single: 'Single press', double: 'Double press', triple: 'Triple press', quadruple: 'Quadruple press',
	hold: 'Hold', release: 'Let go after hold', press: 'Press', multi_press: 'Press',
	long_press: 'Long press', long_release: 'Let go after long press', '*': 'Any press'
};
export const pressLabel = (action: string) =>
	PRESS_WORDS[action] ?? action.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase());

/** Every press "Button pressed" can react to: what each of the device's buttons can actually send.
 * Ids are "<button>:<press>"; the ticked ones become the node's outputs. */
export function pressOptions(dev?: Device, ticked: string[] = []): (Output & { button: string; short: string })[] {
	const buttons = (dev?.entities ?? []).filter((e) => e.kind === 'button');
	return buttons.flatMap((e) => {
		// "Any press" only exists on nodes from before buttons listed their presses.
		const actions = [...(e.actions ?? []), ...(ticked.includes(`${e.key}:*`) ? ['*'] : [])];
		return actions.map((a) => {
			// Grouped inputs (profiles) are listed under their group. A wheel reports its clicks as one multi-press,
			// so it is named by what it does ("Dimmer increase"); a button by what you did ("Button press").
			const short = e.group
				? e.device_class === 'wheel' && a === 'multi_press' ? e.name : `${e.name} ${pressLabel(a).toLowerCase()}`
				: pressLabel(a);
			return {
				id: `${e.key}:${a}`,
				label: e.group ? short : buttons.length > 1 ? `${e.name} · ${short}` : short,
				group: e.group ?? undefined,
				short,
				tone: 'neutral' as const,
				button: e.group ?? e.name
			};
		});
	});
}

/** The connection points on the right of a node. Branching nodes have one per outcome. */
export function outputs(type: string, d: Record<string, any>, devices: Record<string, Device>): Output[] {
	if (type === 'trigger.state') return changeOptions(devices[d.device_id]).filter((o) => (d.outputs ?? []).includes(o.id));
	if (type === 'trigger.event') return pressOptions(devices[d.device_id], d.outputs).filter((o) => (d.outputs ?? []).includes(o.id));
	const e = devices[d.device_id]?.entities.find((x) => x.key === d.key);
	if (type === 'cond.state' && !isNumeric(e)) {
		const words: Record<string, [string, string]> = { occupancy: ['Motion', 'No motion'], presence: ['Someone there', 'Empty'], contact: ['Open', 'Closed'], heat: ['Heating', 'Not heating'] };
		const [on, off] = words[e?.device_class ?? ''] ?? ['On', 'Off'];
		return [
			{ id: 'on', label: on, tone: 'yes' },
			{ id: 'off', label: off, tone: 'no' }
		];
	}
	if (type === 'trigger.control') {
		return [
			{ id: 'on', label: 'Switched on', tone: 'yes' },
			{ id: 'off', label: 'Switched off', tone: 'no' },
			{ id: 'out', label: 'Used (with its value)', tone: 'neutral' }
		];
	}
	if (type === 'trigger.thermostat') {
		const t = Number(d.target ?? 20), m = Number(d.margin ?? 0.5);
		if (Number.isNaN(t) || Number.isNaN(m)) {
			return [
				{ id: 'cold', label: 'Too cold', tone: 'no' },
				{ id: 'warm', label: 'Warm enough', tone: 'yes' }
			];
		}
		return [
			{ id: 'cold', label: `Too cold (${t - m}° or less)`, tone: 'no' },
			{ id: 'warm', label: `Warm enough (${t + m}° or more)`, tone: 'yes' }
		];
	}
	if (type.startsWith('cond.')) {
		return [
			{ id: 'yes', label: 'Yes', tone: 'yes' },
			{ id: 'no', label: 'No', tone: 'no' }
		];
	}
	return [{ id: 'out', label: '', tone: 'neutral' }];
}

/** The output that is true right now, shown green in the editor; null when it cannot be known
 * (actions, button presses, timers, and checks that need history such as "in state for"). */
export function activeOutputs(type: string, id: string, d: Record<string, any>, devices: Record<string, Device>): string[] {
	if (type === 'trigger.state') {
		// Every ticked on/off output whose entity is in that state right now (e.g. "Motion stopped" and "Someone arrives").
		return (devices[d.device_id]?.entities ?? [])
			.flatMap((e) => (typeof e.state === 'boolean' ? [`${e.key}:${e.state ? 'on' : 'off'}`] : []))
			.filter((o) => (d.outputs ?? []).includes(o));
	}
	const one = activeOutput(type, id, d, devices);
	return one ? [one] : [];
}

function activeOutput(type: string, id: string, d: Record<string, any>, devices: Record<string, Device>): string | null {
	if (type === 'trigger.thermostat') return activity.zones[id] ?? null;
	if (type === 'cond.time') {
		const now = new Date().toTimeString().slice(0, 5);
		const from = d.from ?? '00:00', to = d.to ?? '23:59';
		return (from <= to ? from <= now && now < to : now >= from || now < to) ? 'yes' : 'no';
	}
	if (type !== 'cond.state') return null;
	const state = devices[d.device_id]?.entities.find((e) => e.key === d.key)?.state;
	if (typeof state === 'boolean') return state ? 'on' : 'off';
	if (type === 'cond.state' && d.op && state != null) {
		const v = Number(state), want = Number(d.value);
		const yes = d.op === 'gt' ? v > want : d.op === 'lt' ? v < want : String(state) === String(d.value);
		return yes ? 'yes' : 'no';
	}
	return null;
}

/** Sensors and number entities are compared with > < =; everything else is simply on or off. */
export const isNumeric = (e?: { kind: string }) => e?.kind === 'sensor' || e?.kind === 'number';

const OPS: Record<string, string> = { on: 'is on', off: 'is off', eq: '=', gt: '>', lt: '<' };

/** One-line description shown inside a node. */
export function summary(type: string, d: Record<string, any>, devices: Record<string, Device>): string {
	const dev = d.device_id ? (devices[d.device_id]?.name ?? 'missing device') : 'pick a device';
	switch (type) {
		case 'trigger.state':
			return d.device_id && !(d.outputs ?? []).length ? `${dev} · tick what to react to` : dev;
		case 'trigger.event':
			return d.device_id && !(d.outputs ?? []).length ? `${dev} · tick what to react to` : dev;
		case 'trigger.thermostat': {
			const now = devices[d.device_id]?.entities.find((e) => e.key === d.key)?.state;
			const target = typeof d.target === 'string' && d.target.startsWith('{control.') ? 'the target on the card' : `${d.target} °C`;
			return `${dev}: aim for ${target}${typeof now === 'number' ? ` (now ${now} °C)` : ''}`;
		}
		case 'trigger.time':
			return `${d.days?.length ? d.days.map((i: number) => DAY_NAMES[i]).join(', ') : 'every day'} at ${d.at}`;
		case 'trigger.sun':
			return `${d.event === 'sunrise' ? 'sunrise' : 'sunset'}${d.offset ? ` ${d.offset > 0 ? '+' : ''}${d.offset} min` : ''}`;
		case 'trigger.manual':
			return 'when you press Run';
		case 'cond.day':
			return (d.days ?? []).map((i: number) => DAY_NAMES[i]).join(', ') || 'pick days';
		case 'cond.dark':
			return 'sun is down';
		case 'action.throttle':
			return `at most once per ${d.minutes} min`;
		case 'action.http':
			return `${d.method ?? 'GET'} ${d.url}`;
		case 'action.flow':
			return 'run its Run button';
		case 'trigger.interval':
			return `every ${d.seconds}s`;
		case 'cond.state': {
			const e = devices[d.device_id]?.entities.find((x) => x.key === d.key);
			if (!isNumeric(e)) return dev;
			return `${dev} ${OPS[d.op ?? 'gt'] ?? d.op} ${d.value ?? ''}`;
		}
		case 'cond.for':
			return `${dev} ${d.state === 'above' ? `> ${d.value}` : d.state === 'below' ? `< ${d.value}` : d.state} for ${d.minutes} min`;
		case 'cond.time':
			return `${d.from} – ${d.to}`;
		case 'action.device':
			return dev;
		case 'action.cycle':
			return (d.steps ?? []).map((s: unknown) => JSON.stringify(s)).join(' → ');
		case 'action.repeat':
			return `every ${d.seconds}s until stopped`;
		case 'action.delay':
			return `${d.seconds}s`;
		case 'action.timer':
			return `wait ${d.minutes} min, then continue`;
		case 'trigger.control':
			return d.control ? `card control: ${d.control}` : 'pick a card control';
		case 'cond.control':
			return d.control ? `${d.control} is ${d.value === '' || d.value == null ? 'on' : d.value}` : 'pick a card control';
		case 'action.log':
			return String(d.message ?? '');
		case 'action.var':
			return `${d.name} = ${d.value}`;
		case 'cond.var':
			return `${d.name} ${d.op === 'eq' ? '=' : '≠'} ${d.value || '(empty)'}`;
		case 'trigger.webhook':
			return `Phone button "${d.name}" is tapped`;
	}
	const template = DEFS[type]?.summary;
	return template ? template.replace(/\{(\w+)\}/g, (_, key) => String(d[key] ?? '')) : type;
}
