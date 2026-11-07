<script lang="ts">
	import { formatState } from './api.ts';
	import { History } from './history.svelte.ts';
	import { live } from './live.svelte.ts';

	/** bare: no frame or padding, to sit inside a card. */
	let { device_id, key, title, hours = 24, bare = false }: { device_id: string; key: string; title?: string; hours?: number; bare?: boolean } = $props();

	const history = new History(() => ({ device_id, key, hours }));
	const points = $derived(history.points);

	const device = $derived(live.devices[device_id]);
	const entity = $derived(device?.entities.find((e) => e.key === key));
	const W = 300, H = 64, PAD = 4;

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

<div class={bare ? 'bg-base-content/5 rounded-box h-full p-2' : 'bg-base-100 border-base-content/10 rounded-box border p-4'}>
	{#if !device || !entity}
		<p class="text-sm opacity-60">{title ?? 'Sensor'}: this reading is not available ({device_id} · {key}).</p>
	{:else}
		<div class="flex items-baseline justify-between gap-2">
			<span class="min-w-0 truncate text-sm opacity-70">{title || `${device.name} · ${entity.name}`}</span>
			<span class="text-2xl font-bold tabular-nums">{formatState(entity)}</span>
		</div>
		{#if path}
			<svg viewBox="0 0 {W} {H}" class="text-primary mt-2 w-full {bare ? 'h-[calc(100%-2.5rem)]' : 'h-16'}" preserveAspectRatio={bare ? 'none' : undefined} role="img" aria-label="Last {hours} hours">
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
