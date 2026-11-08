<script lang="ts">
	import type { Device, Entity } from '../api.ts';
	import { History } from '../history.svelte.ts';
	import { linePath } from './graphPath.ts';
	import { valueText } from './cardText.ts';
	import type { CardSlot } from './cardDesign.ts';

	/** A card component that draws the last hours of a number: a line, bars (the average of each stretch of time)
	 * or a small sparkline next to the current value. It fills the box it is given. */
	let { device, entity, slot, name, hours: span, fieldKey, labelled = false, text: custom, color = '', colorStyle = '' }: { device: Device; entity: Entity; slot: CardSlot; name: string; hours?: number; fieldKey?: string; labelled?: boolean; text?: string; color?: string; colorStyle?: string } = $props();

	const hours = $derived(span ?? slot.hours ?? 5);
	const history = new History(() => ({ device_id: device.id, key: fieldKey ?? slot.key, hours }));
	const points = $derived(history.points);

	const W = 100, H = 40, PAD = 2, BUCKETS = 24;
	const range = $derived.by(() => {
		if (!points.length) return { min: 0, max: 1 };
		const values = points.map((p) => p.value);
		const min = history.steps ? Math.min(0, ...values) : Math.min(...values), max = Math.max(...values);
		return { min, max: max === min ? min + 1 : max };
	});
	const y = (v: number) => H - PAD - ((v - range.min) / (range.max - range.min)) * (H - 2 * PAD);
	const line = $derived(linePath(points, history.steps, W, PAD, y));
	const area = $derived(line ? `${line} L${W - PAD} ${H} L${PAD} ${H} Z` : '');
	const bars = $derived.by(() => {
		const end = Date.now() / 1000, span = (hours * 3600) / BUCKETS;
		const sums = Array.from({ length: BUCKETS }, () => ({ sum: 0, n: 0 }));
		for (const p of points) {
			const i = Math.min(BUCKETS - 1, Math.max(0, Math.floor((p.ts - (end - hours * 3600)) / span)));
			sums[i].sum += p.value;
			sums[i].n++;
		}
		const lo = Math.min(0, range.min);
		return sums.map((b) => (b.n ? ((b.sum / b.n - lo) / (range.max - lo || 1)) * (H - PAD) : 0));
	});
	const text = $derived(custom ?? valueText(entity, slot));
</script>

<div class="bg-base-content/5 rounded-box relative flex h-full min-h-0 min-w-0 overflow-hidden" class:opacity-50={!device.available}>
	{#if slot.style === 'spark'}
		<div class="flex min-w-0 shrink-0 flex-col justify-center pl-3">
			{#if labelled}<span class="max-w-24 truncate text-xs leading-none opacity-70">{name}</span>{/if}
			<span class="text-lg leading-tight font-bold tabular-nums">{text}</span>
		</div>
		<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" class="{color || 'text-primary'} min-w-0 grow p-1.5" style={colorStyle || undefined} role="img" aria-label="{name}, last {hours} hours">
			<path d={line} fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke" />
		</svg>
	{:else}
		<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" class="{color || 'text-primary'} absolute inset-0 size-full" style={colorStyle || undefined} role="img" aria-label="{name}, last {hours} hours">
			{#if slot.style === 'bars'}
				{#each bars as b, i (i)}
					<rect x={i * (W / BUCKETS) + 0.4} y={H - b} width={W / BUCKETS - 0.8} height={b} fill="currentColor" opacity="0.7" />
				{/each}
			{:else}
				<path d={area} fill="currentColor" opacity="0.15" />
				<path d={line} fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke" />
			{/if}
		</svg>
		<div class="pointer-events-none relative flex min-w-0 items-baseline gap-2 self-start px-2.5 pt-1.5">
			{#if labelled}<span class="min-w-0 truncate text-xs opacity-70">{name}</span>{/if}
			<span class="font-bold tabular-nums">{text}</span>
		</div>
	{/if}
	{#if !line && !(slot.style === 'bars' && points.length)}
		<span class="absolute inset-x-0 bottom-1 text-center text-xs opacity-50">No history yet</span>
	{/if}
</div>
