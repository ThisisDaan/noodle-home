import { api } from './api.ts';
import { live, type HistoryRow } from './live.svelte.ts';

export type HistoryPoint = { ts: number; value: number };

/** The last `hours` of one reading, then new ones as the server pushes them (nothing is polled). Create it while a
 * component is set up; `get` is read again whenever what it returns changes. A number is kept as it is; an on/off or
 * text state becomes a level (off = 0, on = 1, text = its place in the order the words first appeared) and `steps` is
 * true, so a graph draws it as steps. */
export class History {
	points = $state<HistoryPoint[]>([]);
	steps = $state(false);
	#words: string[] = [];

	#level(v: unknown): number | null {
		if (typeof v === 'number') return v;
		if (typeof v === 'boolean') return v ? 1 : 0;
		if (typeof v === 'string') {
			let i = this.#words.indexOf(v);
			if (i < 0) i = this.#words.push(v) - 1;
			return i;
		}
		return null;
	}

	constructor(get: () => { device_id: string; key: string; hours: number }) {
		$effect(() => {
			const { device_id, key, hours } = get();
			const from = Date.now() / 1000 - hours * 3600;
			let alive = true;
			api<{ ts: number; key: string; value: unknown }[]>(`/devices/${encodeURIComponent(device_id)}/history?limit=5000&since=${from}`)
				.then((rows) => {
					if (!alive) return;
					this.#words = [];
					const mine = rows.filter((r) => r.key === key).sort((a, b) => a.ts - b.ts);
					this.steps = mine.some((r) => typeof r.value !== 'number');
					this.points = mine.flatMap((r) => {
						const v = this.#level(r.value);
						return v === null ? [] : [{ ts: r.ts, value: v }];
					});
				})
				.catch(() => {});
			const onRow = (row: HistoryRow) => {
				const v = row.device_id === device_id && row.key === key ? this.#level(row.value) : null;
				if (v === null) return;
				if (typeof row.value !== 'number') this.steps = true;
				this.points = [...this.points.filter((p) => p.ts >= Date.now() / 1000 - hours * 3600), { ts: row.ts, value: v }];
			};
			live.historyListeners.add(onRow);
			return () => {
				alive = false;
				live.historyListeners.delete(onRow);
			};
		});
	}
}
