import { api } from './api.ts';
import { live, type HistoryRow } from './live.svelte.ts';

export type HistoryPoint = { ts: number; value: number };

/** The last `hours` of one reading, then new ones as the server pushes them (nothing is polled). Create it while a
 * component is set up; `get` is read again whenever what it returns changes. */
export class History {
	points = $state<HistoryPoint[]>([]);

	constructor(get: () => { device_id: string; key: string; hours: number }) {
		$effect(() => {
			const { device_id, key, hours } = get();
			const from = Date.now() / 1000 - hours * 3600;
			let alive = true;
			api<{ ts: number; key: string; value: unknown }[]>(`/devices/${encodeURIComponent(device_id)}/history?limit=5000&since=${from}`)
				.then((rows) => {
					if (!alive) return;
					this.points = rows
						.filter((r) => r.key === key && typeof r.value === 'number')
						.map((r) => ({ ts: r.ts, value: r.value as number }))
						.sort((a, b) => a.ts - b.ts);
				})
				.catch(() => {});
			const onRow = (row: HistoryRow) => {
				if (row.device_id === device_id && row.key === key && typeof row.value === 'number') {
					this.points = [...this.points.filter((p) => p.ts >= Date.now() / 1000 - hours * 3600), { ts: row.ts, value: row.value }];
				}
			};
			live.historyListeners.add(onRow);
			return () => {
				alive = false;
				live.historyListeners.delete(onRow);
			};
		});
	}
}
