<script lang="ts">
	/** A remote's wheel as a control: "−" and "+" either side of a knob. Turn the knob (drag it around its centre)
	 * and every 25° it sends one "decrease" or "increase"; tap it to press the remote's own button. The − and +
	 * buttons send one step each, for a keyboard or a quick tap. Nothing here knows what a step does: the
	 * parent turns steps and taps into presses. */
	let { label, onstep, ontap }: { label: string; onstep: (direction: 1 | -1) => void; ontap?: () => void } = $props();

	const STEP = 25; // degrees of turning per step
	let angle = $state(0);
	let knob: HTMLButtonElement | undefined;
	let drag: { last: number; moved: number; carry: number } | null = null;

	const at = (e: PointerEvent) => {
		const r = knob!.getBoundingClientRect();
		return (Math.atan2(e.clientY - (r.top + r.height / 2), e.clientX - (r.left + r.width / 2)) * 180) / Math.PI;
	};

	function down(e: PointerEvent) {
		knob!.setPointerCapture(e.pointerId);
		drag = { last: at(e), moved: 0, carry: 0 };
	}
	function move(e: PointerEvent) {
		if (!drag) return;
		const now = at(e);
		let delta = now - drag.last;
		if (delta > 180) delta -= 360;
		if (delta < -180) delta += 360;
		drag.last = now;
		drag.moved += Math.abs(delta);
		drag.carry += delta;
		angle += delta;
		while (Math.abs(drag.carry) >= STEP) {
			const direction = drag.carry > 0 ? 1 : -1;
			drag.carry -= direction * STEP;
			onstep(direction);
		}
	}
	function up() {
		if (drag && drag.moved < 6) ontap?.(); // a tap, not a turn
		drag = null;
	}
	function key(e: KeyboardEvent) {
		if (e.key === 'ArrowRight' || e.key === 'ArrowUp') (e.preventDefault(), (angle += STEP), onstep(1));
		else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') (e.preventDefault(), (angle -= STEP), onstep(-1));
		else if ((e.key === 'Enter' || e.key === ' ') && ontap) (e.preventDefault(), ontap());
	}
</script>

<div class="bg-base-content/10 flex h-12 flex-none items-center rounded-full" role="group" aria-label={label}>
	<button type="button" class="btn btn-ghost btn-circle size-9 min-h-0 text-xl active:scale-90" aria-label="{label}: decrease"
		onclick={() => ((angle -= STEP), onstep(-1))}>−</button>
	<button type="button" bind:this={knob} aria-label="{label}: turn the knob, or tap to press"
		class="bg-base-100 border-base-content/20 relative size-11 flex-none cursor-grab touch-none rounded-full border shadow-md active:cursor-grabbing"
		style="transform: rotate({angle}deg)"
		onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={() => (drag = null)} onkeydown={key}>
		<span class="bg-primary absolute top-1 left-1/2 size-2 -translate-x-1/2 rounded-full"></span>
	</button>
	<button type="button" class="btn btn-ghost btn-circle size-9 min-h-0 text-xl active:scale-90" aria-label="{label}: increase"
		onclick={() => ((angle += STEP), onstep(1))}>+</button>
</div>
