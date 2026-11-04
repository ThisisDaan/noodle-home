import type { Device } from './api';
import { applyActivity, type FlowMessage } from './flow/activity.svelte.ts';
import { layout, type SavedLayout } from './layout.svelte.ts';

export type FlowSummary = { id: string; name: string; enabled: boolean; last_run: number | null; last_error: string | null; nodes: number; manual?: boolean };
export type Variables = Record<string, { value: string; updated: number }>;
export type LogLine = { time: number; message: string };
export type HistoryRow = { device_id: string; key: string; ts: number; value: boolean | number | string | null };

type Message =
	| { type: 'snapshot'; devices: Device[]; areas: string[] }
	| { type: 'areas'; areas: string[] }
	| { type: 'layout'; layout: SavedLayout }
	| { type: 'flows'; flows: FlowSummary[] }
	| { type: 'variables'; variables: Variables }
	| { type: 'log'; flow_id: string; line: LogLine }
	| { type: 'device'; device: Device }
	| { type: 'removed'; id: string }
	| ({ type: 'history' } & HistoryRow)
	| FlowMessage;

/** Devices, areas, flows, variables and flow log lines: the server pushes every change over /api/ws, nothing is polled.
 * Pages fetch their starting point once (flows, variables), then these stay current. */
class Live {
	devices = $state<Record<string, Device>>({});
	areas = $state<string[]>([]);
	flows = $state<FlowSummary[] | null>(null);
	variables = $state<Variables | null>(null);
	/** Called with each new flow log line. */
	logListeners = new Set<(flowId: string, line: LogLine) => void>();
	/** Called with each new history row of any device. */
	historyListeners = new Set<(row: HistoryRow) => void>();
	connected = $state(false);

	#ws: WebSocket | null = null;
	#ping: ReturnType<typeof setInterval> | undefined;
	#stopped = true;

	get list(): Device[] {
		return Object.values(this.devices).sort((a, b) => a.name.localeCompare(b.name));
	}

	start() {
		if (!this.#stopped) return;
		this.#stopped = false;
		this.#connect();
	}

	stop() {
		this.#stopped = true;
		clearInterval(this.#ping);
		this.#ws?.close();
		this.#ws = null;
		this.connected = false;
	}

	#connect() {
		const proto = location.protocol === 'https:' ? 'wss' : 'ws';
		const ws = new WebSocket(`${proto}://${location.host}/api/ws`);
		this.#ws = ws;
		ws.onopen = () => {
			this.connected = true;
			this.#ping = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send('ping'), 25000);
		};
		ws.onmessage = (ev) => {
			const msg = JSON.parse(ev.data) as Message;
			if (msg.type === 'snapshot') {
				this.devices = Object.fromEntries(msg.devices.map((d) => [d.id, d]));
				this.areas = msg.areas;
			} else if (msg.type === 'areas') {
				this.areas = msg.areas;
			} else if (msg.type === 'layout') {
				layout.apply(msg.layout); // someone edited dashboard.yaml
			} else if (msg.type === 'device') {
				this.devices[msg.device.id] = msg.device;
			} else if (msg.type === 'removed') {
				delete this.devices[msg.id];
			} else if (msg.type === 'flows') {
				this.flows = msg.flows;
			} else if (msg.type === 'variables') {
				this.variables = msg.variables;
			} else if (msg.type === 'log') {
				for (const listener of this.logListeners) listener(msg.flow_id, msg.line);
			} else if (msg.type === 'history') {
				for (const listener of this.historyListeners) listener(msg);
			} else if (msg.type === 'flow') {
				applyActivity(msg.flow_id, msg.passed, msg.waiting, msg.zones);
			}
		};
		ws.onclose = () => {
			this.connected = false;
			clearInterval(this.#ping);
			if (!this.#stopped) setTimeout(() => this.#connect(), 3000);
		};
	}
}

export const live = new Live();
