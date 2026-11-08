<script lang="ts">
	import { History } from '../history.svelte.ts';
	import { linePath } from './graphPath.ts';
	import type { Part } from './cardText.ts';

	/** A small graph inside a line of text ({device.brightness.history}): the last hours of a field, drawn in the
	 * text's colour and as tall as the text. It grows with the text size. */
	let { graph }: { graph: NonNullable<Part['graph']> } = $props();

	const history = new History(() => ({ device_id: graph.deviceId, key: graph.key, hours: graph.hours }));
	const points = $derived(history.points);

	const W = 100, H = 30, PAD = 2, BUCKETS = 24;
	const range = $derived.by(() => {
		if (!points.length) return { min: 0, max: 1 };
		const values = points.map((p) => p.value);
		const min = history.steps ? Math.min(0, ...values) : Math.min(...values), max = Math.max(...values);
		return { min, max: max === min ? min + 1 : max };
	});
	const y = (v: number) => H - PAD - ((v - range.min) / (range.max - range.min)) * (H - 2 * PAD);
	const line = $derived(linePath(points, history.steps, W, PAD, y));
	const bars = $derived.by(() => {
		const end = Date.now() / 1000, span = (graph.hours * 3600) / BUCKETS;
		const sums = Array.from({ length: BUCKETS }, () => ({ sum: 0, n: 0 }));
		for (const p of points) {
			const i = Math.min(BUCKETS - 1, Math.max(0, Math.floor((p.ts - (end - graph.hours * 3600)) / span)));
			sums[i].sum += p.value;
			sums[i].n++;
		}
		const lo = Math.min(0, range.min);
		return sums.map((b) => (b.n ? ((b.sum / b.n - lo) / (range.max - lo || 1)) * (H - PAD) : 0));
	});
</script>

<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" class="inline-block h-[1.5em] w-[6em] align-middle" role="img" aria-label="Last {graph.hours} hours">
	{#if graph.bars}
		{#each bars as b, i (i)}
			<rect x={i * (W / BUCKETS) + 0.4} y={H - b} width={W / BUCKETS - 0.8} height={b} fill="currentColor" opacity="0.7" />
		{/each}
	{:else if line}
		<path d={line} fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke" />
	{:else}
		<path d="M{PAD} {H / 2} L{W - PAD} {H / 2}" fill="none" stroke="currentColor" stroke-width="1" stroke-dasharray="3 3" opacity="0.4" vector-effect="non-scaling-stroke" />
	{/if}
</svg>
