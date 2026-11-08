import type { HistoryPoint } from '../history.svelte.ts';

/** The path of a history graph. A number is a line from point to point; an on/off or text state (`steps`) holds its
 * value until it changes, so it is a step line that runs on to now. Empty when there is nothing to draw. */
export function linePath(points: HistoryPoint[], steps: boolean, W: number, PAD: number, y: (v: number) => number): string {
	if (!points.length || (points.length < 2 && !steps)) return '';
	const t0 = points[0].ts;
	const last = points[points.length - 1];
	const t1 = steps ? Math.max(Date.now() / 1000, last.ts) : last.ts;
	const x = (ts: number) => (PAD + ((ts - t0) / (t1 - t0 || 1)) * (W - 2 * PAD)).toFixed(2);
	let d = `M${x(t0)} ${y(points[0].value).toFixed(2)}`;
	for (let i = 1; i < points.length; i++) {
		const p = points[i];
		if (steps) d += ` L${x(p.ts)} ${y(points[i - 1].value).toFixed(2)}`;
		d += ` L${x(p.ts)} ${y(p.value).toFixed(2)}`;
	}
	if (steps) d += ` L${x(t1)} ${y(last.value).toFixed(2)}`;
	return d;
}
