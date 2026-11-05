<script lang="ts">
	/** One big bar to drag for a 0-100 level. Shows the percentage (or `zeroLabel` at 0); `oncommit` fires on
	 * release. `tone` is the fill colour. */
	let { value, label, tone = 'primary', zeroLabel = 'Off', dragging = $bindable(null), oncommit }: {
		value: number;
		label: string;
		tone?: 'primary' | 'warning' | 'success';
		zeroLabel?: string;
		dragging?: number | null;
		oncommit: (value: number) => void;
	} = $props();

	const fills = { primary: 'bg-primary/50', warning: 'bg-warning/50', success: 'bg-success/50' };
</script>

<div class="bg-base-content/10 rounded-box relative h-12 grow overflow-hidden">
	<div class="{fills[tone]} absolute inset-y-0 left-0" style="width: {value}%"></div>
	<input type="range" min="0" max="100" {value} aria-label={label}
		class="absolute inset-0 size-full cursor-pointer opacity-0"
		oninput={(e) => (dragging = Number(e.currentTarget.value))}
		onchange={(e) => {
			dragging = null;
			oncommit(Number(e.currentTarget.value));
		}} />
	<span class="pointer-events-none absolute inset-0 grid place-items-center font-bold tabular-nums">
		{value > 0 ? `${value}%` : zeroLabel}
	</span>
</div>
