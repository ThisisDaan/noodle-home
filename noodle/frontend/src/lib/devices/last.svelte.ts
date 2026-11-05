import { api } from '../api.ts';
import { live, type HistoryRow } from '../live.svelte.ts';

export type Last = { ts: number; value: HistoryRow['value'] };

/** When each of a device's entities last changed, and to what: the latest history row per key. Fetched once,
 * then kept up to date by the rows the server pushes (nothing is polled). Call it while a component starts up.
 * `now` ticks every 30 s while the component is shown, so "5m ago" stays right. */
export function lastChanges(deviceId: () => string) {
	let rows = $state<Record<string, Last>>({});
	let now = $state(Date.now());

	$effect(() => {
		const id = deviceId();
		let alive = true;
		rows = {};
		api<{ ts: number; key: string; value: HistoryRow['value'] }[]>(`/devices/${encodeURIComponent(id)}/history?limit=200`)
			.then((list) => {
				if (!alive) return;
				const latest: Record<string, Last> = {};
				for (const r of list) if (!(r.key in latest) || r.ts > latest[r.key].ts) latest[r.key] = { ts: r.ts, value: r.value };
				rows = { ...latest, ...rows };
			})
			.catch(() => {});
		const onRow = (row: HistoryRow) => {
			if (row.device_id === id) rows = { ...rows, [row.key]: { ts: row.ts, value: row.value } };
		};
		live.historyListeners.add(onRow);
		const timer = setInterval(() => (now = Date.now()), 30000);
		return () => {
			alive = false;
			live.historyListeners.delete(onRow);
			clearInterval(timer);
		};
	});

	return {
		get: (key: string): Last | undefined => rows[key],
		/** "just now", "5m ago", ... for an entity, or "no activity yet". */
		ago(key: string): string {
			void now;
			const ts = rows[key]?.ts;
			if (!ts) return 'no activity yet';
			const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
			return s < 10 ? 'just now' : s < 60 ? `${s}s ago` : s < 3600 ? `${Math.round(s / 60)}m ago` : s < 86400 ? `${Math.round(s / 3600)}h ago` : `${Math.round(s / 86400)}d ago`;
		}
	};
}
