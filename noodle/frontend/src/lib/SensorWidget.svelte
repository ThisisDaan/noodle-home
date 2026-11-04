<script lang="ts">
	import { api, formatState } from './api.ts';
	import { live, type HistoryRow } from './live.svelte.ts';

	let { device_id, key, title, hours = 24 }: { device_id: string; key: string; title?: string; hours?: number } = $props();

	type Point = { ts: number; value: number };
	let points = $state<Point[]>([]);

	const device = $derived(live.devices[device_id]);
	const entity = $derived(device?.entities.find((e) => e.key === key));
	const W = 300, H = 64, PAD = 4;

	// The last `hours` of readings, then new ones as the server pushes them (nothing is polled).
	$effect(() => {
		const from = Date.now() / 1000 - hours * 3600;
		let alive = true;
		api<{ ts: number; key: string; value: unknown }[]>(`/devices/${encodeURIComponent(device_id)}/history?limit=5000&since=${from}`)
			.then((rows) => {
				if (!alive) return;
				points = rows
					.filter((r) => r.key === key && typeof r.value === 'number')
					.map((r) => ({ ts: r.ts, value: r.value as number }))
					.sort((a, b) => a.ts - b.ts);
			})
			.catch(() => {});
		const onRow = (row: HistoryRow) => {
			if (row.device_id === device_id && row.key === key && typeof row.value === 'number') {
				points = [...points.filter((p) => p.ts >= Date.now() / 1000 - hours * 3600), { ts: row.ts, value: row.value }];
			}
		};
		live.historyListeners.add(onRow);
		return () => {
			alive = false;
			live.historyListeners.delete(onRow);
		};
	});

	const range = $derived.by(() => {
		if (!points.length) return null;
		const values = points.map((p) => p.value);
		return { min: Math.min(...values), max: Math.max(...values) };
	});

	const path = $derived.by(() => {
		if (!range || points.length < 2) return '';
		const t0 = points[0].ts, t1 = points[points.length - 1].ts || t0 + 1;
		const span = range.max - range.min || 1;
		return points
			.map((p, i) => {
				const x = PAD + ((p.ts - t0) / (t1 - t0 || 1)) * (W - 2 * PAD);
				const y = H - PAD - ((p.value - range.min) / span) * (H - 2 * PAD);
				return `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`;
			})
			.join(' ');
	});
</script>

<div class="bg-base-100 border-base-content/10 rounded-box border p-4">
	{#if !device || !entity}
		<p class="text-sm opacity-60">{title ?? 'Sensor'}: this reading is not available ({device_id} · {key}).</p>
	{:else}
		<div class="flex items-baseline justify-between gap-2">
			<span class="min-w-0 truncate text-sm opacity-70">{title || `${device.name} · ${entity.name}`}</span>
			<span class="text-2xl font-bold tabular-nums">{formatState(entity)}</span>
		</div>
		{#if path}
			<svg viewBox="0 0 {W} {H}" class="text-primary mt-2 h-16 w-full" role="img" aria-label="Last {hours} hours">
				<path d={path} fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke" />
			</svg>
			<div class="flex justify-between text-xs opacity-50">
				<span>{range ? `${range.min}${entity.unit ? ' ' + entity.unit : ''} low` : ''}</span>
				<span>last {hours < 48 ? `${hours} h` : `${Math.round(hours / 24)} days`}</span>
				<span>{range ? `${range.max}${entity.unit ? ' ' + entity.unit : ''} high` : ''}</span>
			</div>
		{:else}
			<p class="mt-2 text-xs opacity-50">No history in the last {hours} hours yet.</p>
		{/if}
	{/if}
</div>
