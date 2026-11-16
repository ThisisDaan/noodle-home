<script lang="ts">
	import { BarController, BarElement, CategoryScale, Chart, Filler, LinearScale, LineController, LineElement, PointElement, Tooltip } from 'chart.js';
	import { formatState, type Device, type Entity } from './api';

	Chart.register(BarController, BarElement, CategoryScale, Filler, LinearScale, LineController, LineElement, PointElement, Tooltip);

	type Row = { ts: number; key: string; value: boolean | number | string | null };
	/** One block of time. avg is the time-weighted average (for on/off: the share of the block it was on, 0..1). */
	type Block = { start: number; avg: number; min: number; max: number };
	type Series = { entity: Entity; bool: boolean; last: number; blocks: (Block | null)[] };

	let { device, rows, from, to, size }: { device: Device; rows: Row[]; from: number; to: number; size: number } = $props();

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
			out.push({ entity, bool, last: Number(mine[mine.length - 1].value), blocks });
		}
		return out;
	});

	const tidy = (v: number) => Math.round(v * 10) / 10; // averages come out like 9.039948958, show 9
	const show = (s: Series, v: number) => formatState({ ...s.entity, state: s.bool ? v === 1 : tidy(v) });
	const span = (seconds: number) => (seconds >= 86400 && seconds % 86400 === 0 ? `${seconds / 86400} d` : seconds >= 3600 && seconds % 3600 === 0 ? `${seconds / 3600} h` : `${seconds / 60} min`);
	const total = $derived(count * size);
	const tickText = (ts: number) => {
		const d = new Date(ts * 1000);
		if (total <= 86400 * 1.5) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
		if (total <= 86400 * 3) return d.toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' });
		return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
	};
	const fullText = (ts: number) => new Date(ts * 1000).toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
	const readout = (s: Series, b: Block) => (s.bool ? `On ${Math.round(b.avg * 100)}% of the time` :
		b.min === b.max ? show(s, b.avg) : `${show(s, b.avg)} (${show(s, b.min)} to ${show(s, b.max)})`);

	/** Draws one series with Chart.js on a canvas; redrawn when the data changes, destroyed when the card goes away. */
	function draw(s: Series) {
		return (canvas: HTMLCanvasElement) => {
			const css = getComputedStyle(canvas);
			const ink = css.color; // set by text-base-content on the canvas
			const accent = css.getPropertyValue('--chart-accent').trim() || css.color;
			const grid = 'color-mix(in oklab, ' + ink + ' 15%, transparent)';
			const labels = s.blocks.map((_, i) => first + i * size);
			const index = (v: unknown) => labels[Number(v)] ?? 0;
			const tip = { display: false };
			const datasets = s.bool
				? [{ type: 'bar' as const, data: s.blocks.map((b) => (b ? b.avg : null)), backgroundColor: accent, borderRadius: 2, categoryPercentage: 1, barPercentage: 0.9 }]
				: [
					{ type: 'line' as const, data: s.blocks.map((b) => (b ? b.max : null)), borderWidth: 0, pointRadius: 0, pointHitRadius: 0, backgroundColor: 'transparent', fill: false },
					{ type: 'line' as const, data: s.blocks.map((b) => (b ? b.min : null)), borderWidth: 0, pointRadius: 0, pointHitRadius: 0, fill: '-1', backgroundColor: 'color-mix(in oklab, ' + accent + ' 22%, transparent)' },
					{ type: 'line' as const, data: s.blocks.map((b) => (b ? b.avg : null)), borderColor: accent, backgroundColor: accent, borderWidth: 2.5, tension: 0.25, pointRadius: count <= 40 ? 3 : 0, pointHoverRadius: 6, pointHitRadius: 20, spanGaps: false }
				];
			const chart = new Chart(canvas, {
				type: s.bool ? 'bar' : 'line',
				data: { labels, datasets: datasets as never },
				options: {
					responsive: true,
					maintainAspectRatio: false,
					animation: false,
					interaction: { mode: 'index', intersect: false },
					layout: { padding: { top: 6, right: 4 } },
					scales: {
						x: { grid: { display: false }, border: { color: grid }, ticks: { color: ink, maxRotation: 0, autoSkip: true, maxTicksLimit: 5, font: { size: 12 }, callback: (v) => tickText(index(v)) } },
						y: s.bool
							? { min: 0, max: 1, grid: { color: grid }, border: { display: false }, ticks: { color: ink, stepSize: 1, font: { size: 12 }, callback: (v) => (v ? 'On' : 'Off') } }
							: { grace: '8%', grid: { color: grid }, border: { display: false }, ticks: { color: ink, maxTicksLimit: 5, font: { size: 12 }, callback: (v) => show(s, Number(v)) } }
					},
					plugins: {
						legend: tip,
						tooltip: {
							filter: (item) => item.datasetIndex === datasets.length - 1,
							displayColors: false,
							padding: 10,
							bodyFont: { size: 14, weight: 'bold' },
							titleFont: { size: 12, weight: 'normal' },
							callbacks: {
								title: (items) => fullText(index(items[0].dataIndex)),
								label: (item) => { const b = s.blocks[item.dataIndex]; return b ? readout(s, b) : 'No data'; }
							}
						}
					}
				}
			});
			return () => chart.destroy();
		};
	}
</script>

{#each series as s (s.entity.key)}
	<div class="bg-base-200 rounded-box flex flex-col gap-1 p-3">
		<div class="flex items-baseline justify-between gap-2">
			<span class="truncate text-sm font-medium">{device.entities.length > 1 ? s.entity.name : `Per ${span(size)}`}</span>
			<span class="text-sm font-semibold tabular-nums">{show(s, s.last)} <span class="text-xs font-normal opacity-60">now</span></span>
		</div>
		<div class="relative h-52 w-full touch-pan-y">
			<canvas {@attach draw(s)} class="text-base-content [--chart-accent:var(--color-primary)]" aria-label="{s.entity.name} per {span(size)}"></canvas>
		</div>
		<span class="text-xs opacity-60">Line is the average per {span(size)}{s.bool ? '' : '; the shaded band is the lowest to highest'}. Touch the chart to read a value.</span>
	</div>
{/each}
