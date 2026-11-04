<script lang="ts">
	import { formatState, type Device, type Entity } from './api';

	type Row = { ts: number; key: string; value: boolean | number | string | null };
	/** One block of time. avg is the time-weighted average (for on/off: the share of the block it was on, 0..1). */
	type Block = { start: number; avg: number; min: number; max: number };
	type Series = { entity: Entity; bool: boolean; last: number; blocks: (Block | null)[]; min: number; max: number };

	let { device, rows, from, to, size }: { device: Device; rows: Row[]; from: number; to: number; size: number } = $props();

	const W = 300, H = 70, PAD = 4;

	const first = $derived(Math.floor(from / size) * size); // blocks line up with the clock (e.g. :00, :15, :30)
	const count = $derived(Math.max(1, Math.ceil((to - first) / size)));

	/** Cut each reading into blocks. A value holds until the next change, so every block gets the average of what it was. */
	const series = $derived.by(() => {
		const out: Series[] = [];
		for (const entity of device.entities) {
			const mine = rows.filter((r) => r.key === entity.key && (typeof r.value === 'number' || typeof r.value === 'boolean')).reverse();
			if (!mine.length) continue;
			const bool = typeof mine[0].value === 'boolean';
			const acc = Array.from({ length: count }, () => ({ w: 0, sum: 0, min: Infinity, max: -Infinity }));
			mine.forEach((r, i) => {
				const v = Number(r.value), s = r.ts, e = mine[i + 1]?.ts ?? to;
				for (let b = Math.max(0, Math.floor((s - first) / size)); b < count && first + b * size < e; b++) {
					const w = Math.min(e, first + (b + 1) * size) - Math.max(s, first + b * size);
					if (w <= 0) continue;
					acc[b].w += w; acc[b].sum += v * w; acc[b].min = Math.min(acc[b].min, v); acc[b].max = Math.max(acc[b].max, v);
				}
			});
			const blocks = acc.map((a, b) => (a.w ? { start: first + b * size, avg: a.sum / a.w, min: a.min, max: a.max } : null));
			const seen = blocks.filter((b): b is Block => !!b);
			let min = Math.min(...seen.map((b) => b.min)), max = Math.max(...seen.map((b) => b.max));
			if (min === max) { min -= 1; max += 1; }
			out.push({ entity, bool, last: Number(mine[mine.length - 1].value), blocks, min, max });
		}
		return out;
	});

	const slot = $derived(W / count);
	const y = (s: Series, v: number) => PAD + (1 - (v - s.min) / (s.max - s.min)) * (H - 2 * PAD);

	const tidy = (v: number) => Math.round(v * 10) / 10; // averages come out like 9.039948958, show 9
	const show = (s: Series, v: number) => formatState({ ...s.entity, state: s.bool ? v === 1 : tidy(v) });
	const span = (seconds: number) => (seconds >= 86400 && seconds % 86400 === 0 ? `${seconds / 86400} d` : seconds >= 3600 && seconds % 3600 === 0 ? `${seconds / 3600} h` : `${seconds / 60} min`);
	const when = (ts: number) => new Date(ts * 1000).toLocaleString([], to - first <= 86400 * 1.5
		? { hour: '2-digit', minute: '2-digit' } : { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
	const readout = (s: Series, b: Block) => (s.bool ? `On ${Math.round(b.avg * 100)}% of the time` :
		b.min === b.max ? show(s, b.avg) : `${show(s, b.avg)} (${show(s, b.min)} to ${show(s, b.max)})`);

	let hover = $state<number | null>(null); // block index under the pointer
	function move(e: PointerEvent) {
		const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
		hover = Math.max(0, Math.min(count - 1, Math.floor(((e.clientX - rect.left) / rect.width) * count)));
	}
</script>

{#each series as s (s.entity.key)}
	{@const b = hover === null ? null : s.blocks[hover]}
	<div class="bg-base-200 rounded-box flex flex-col gap-1 p-3">
		<span class="truncate text-sm font-medium">{device.entities.length > 1 ? s.entity.name : `Per ${span(size)}`}</span>
		<!-- fixed height, so the page does not move while the text changes under the pointer -->
		<p class="h-5 truncate text-sm tabular-nums">
			{#if hover !== null}
				{b ? readout(s, b) : 'No data'}<span class="ml-2 text-xs opacity-60">{when(first + hover * size)}</span>
			{:else}
				{show(s, s.last)}<span class="ml-2 text-xs opacity-60">now</span>
			{/if}
		</p>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="relative touch-pan-y" onpointermove={move} onpointerleave={() => (hover = null)}>
			<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" class="h-24 w-full" role="img" aria-label="{s.entity.name} per {span(size)}">
				{#each s.blocks as blk, i (i)}
					{#if hover === i}<rect x={i * slot} y="0" width={slot} height={H} class="fill-base-content/10" />{/if}
					{#if blk}
						{#if s.bool}
							<rect x={i * slot + slot * 0.1} y={H - blk.avg * (H - PAD)} width={slot * 0.8} height={blk.avg * (H - PAD)} class="fill-primary/80" />
						{:else}
							<!-- the bar spans the lowest to the highest value in the block; the line is the average -->
							<rect x={i * slot + slot * 0.1} y={y(s, blk.max)} width={slot * 0.8} height={Math.max(2, y(s, blk.min) - y(s, blk.max))} class="fill-primary/35" />
							<rect x={i * slot + slot * 0.1} y={y(s, blk.avg) - 1} width={slot * 0.8} height="2" class="fill-primary" />
						{/if}
					{/if}
				{/each}
				<line x1="0" x2={W} y1={H} y2={H} class="stroke-base-content/20" vector-effect="non-scaling-stroke" />
			</svg>
			<span class="pointer-events-none absolute top-0 left-0 text-[10px] opacity-60">{s.bool ? 'Always on' : show(s, s.max)}</span>
			<span class="pointer-events-none absolute bottom-0 left-0 text-[10px] opacity-60">{s.bool ? '' : show(s, s.min)}</span>
		</div>
		<div class="flex justify-between text-[10px] opacity-60"><span>{when(first)}</span><span>{when(to)}</span></div>
	</div>
{/each}
