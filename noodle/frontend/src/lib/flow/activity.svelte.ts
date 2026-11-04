/** Live state of the flow open in the editor: loaded once, then updated by "flow" messages on the WebSocket. */
export const activity = $state({
	flowId: '',
	/** Connections a message went along in the last few seconds. */
	passed: [] as string[],
	/** Timer node id -> when it runs out (local Date.now() time). */
	waiting: {} as Record<string, number>,
	/** Thermostat node id -> "cold" / "warm", the output it last fired. */
	zones: {} as Record<string, string>,
	/** Ticks every second while a timer counts down, so the countdown text updates. */
	now: Date.now()
});

export type FlowMessage = {
	type: 'flow';
	flow_id: string;
	passed?: string[];
	waiting?: Record<string, number | null>;
	zones?: Record<string, string>;
};

let tick: ReturnType<typeof setInterval> | undefined;

/** Show `passed` connections green for a few seconds; `waiting` holds seconds left per timer (null = stopped). */
export function applyActivity(flowId: string, passed: string[] = [], waiting: Record<string, number | null> = {},
	zones: Record<string, string> = {}) {
	if (flowId !== activity.flowId) return;
	Object.assign(activity.zones, zones);
	if (passed.length) {
		activity.passed = [...activity.passed, ...passed];
		setTimeout(() => (activity.passed = activity.passed.filter((id) => !passed.includes(id))), 4000);
	}
	for (const [node, left] of Object.entries(waiting)) {
		if (left === null) delete activity.waiting[node];
		else activity.waiting[node] = Date.now() + left * 1000;
	}
	clearInterval(tick);
	activity.now = Date.now();
	if (Object.keys(activity.waiting).length) tick = setInterval(() => (activity.now = Date.now()), 1000);
}

export function resetActivity(flowId = '') {
	clearInterval(tick);
	Object.assign(activity, { flowId, passed: [], waiting: {}, zones: {}, now: Date.now() });
}
