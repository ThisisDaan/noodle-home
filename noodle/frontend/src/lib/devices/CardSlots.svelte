<script lang="ts">
	import type { Device } from '../api.ts';
	import CardComponent from './CardComponent.svelte';
	import { COMPONENTS, SIZES, columns, type CardDesign } from './cardDesign.ts';

	/** The body of a designed card: its components in their slots. Small and wide cards have one row of 3rem, a
	 * large card shares the height between its rows. */
	let { device, design, labelled = false }: { device: Device; design: CardDesign; labelled?: boolean } = $props();
	const size = $derived(SIZES[design.size]);
</script>

<div class="grid min-h-0 gap-2 {design.size === 'large' ? 'grow' : 'h-12'}"
	style="grid-template-columns: {columns(design, labelled)}; grid-template-rows: repeat({size.rows}, minmax(0, 1fr));">
	{#each design.slots as slot (slot.at)}
		{@const c = COMPONENTS[slot.component]}
		<div class="min-w-0" style="grid-column: {(slot.at % size.cols) + 1} / span {c.w}; grid-row: {Math.floor(slot.at / size.cols) + 1} / span {c.h};">
			<CardComponent {device} {slot} {labelled} />
		</div>
	{/each}
</div>
