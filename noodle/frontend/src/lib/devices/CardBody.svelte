<script lang="ts">
	import type { Device } from '../api.ts';
	import CardComponent from './CardComponent.svelte';
	import { grid, type CardDesign, type CardSlot } from './cardDesign.ts';

	type Editor = {
		selected: number | null;
		/** a pointer went down on a component (index) to move it, or on one of its edges to resize it */
		down: (e: PointerEvent, index: number, mode: 'move' | 'e' | 's' | 'se') => void;
	};

	/** The body of a card: its components on the card's fine grid. The dashboard and the designer draw it with this
	 * same component, so the designer shows exactly what the card will look like. With `editor` the components are
	 * not live (they can be grabbed instead) and the empty grid shows. */
	let { device, design, labelled = false, editor, el = $bindable() }: {
		device: Device; design: CardDesign; labelled?: boolean; editor?: Editor; el?: HTMLElement;
	} = $props();

	const g = $derived(grid(design));
	const place = (s: Pick<CardSlot, 'x' | 'y' | 'w' | 'h'>) => `grid-column: ${s.x + 1} / span ${s.w}; grid-row: ${s.y + 1} / span ${s.h};`;
</script>

<div bind:this={el} class="relative grid h-full min-h-0 gap-1.5" style="grid-template-columns: repeat({g.cols}, minmax(0, 1fr)); grid-template-rows: repeat({g.rows}, minmax(0, 1fr));">
	{#if editor}
		{#each Array.from({ length: g.cols * g.rows }, (_, i) => i) as i (i)}
			<div class="grid place-items-center" style="grid-column: {(i % g.cols) + 1}; grid-row: {Math.floor(i / g.cols) + 1};" aria-hidden="true">
				<span class="bg-base-content/25 size-1 rounded-full"></span>
			</div>
		{/each}
	{/if}
	{#each design.slots as slot, i (i)}
		<div class="relative min-w-0" style={place(slot)}>
			<div class="size-full {editor ? 'pointer-events-none select-none' : ''}" inert={!!editor}><CardComponent {device} {slot} {labelled} preview={!!editor} /></div>
			{#if editor}
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<div data-slot class="absolute inset-0 cursor-move touch-none rounded-lg {editor.selected === i ? 'outline-primary bg-primary/10 outline-2' : 'hover:outline-primary/40 hover:outline-2'}"
					onpointerdown={(e) => editor.down(e, i, 'move')}>
					{#if editor.selected === i}
						<!-- svelte-ignore a11y_no_static_element_interactions -->
						<span class="absolute inset-y-2 -right-1.5 w-3 cursor-ew-resize touch-none" onpointerdown={(e) => { e.stopPropagation(); editor.down(e, i, 'e'); }}>
							<span class="bg-primary absolute inset-y-0 left-1 w-1 rounded-full"></span></span>
						<!-- svelte-ignore a11y_no_static_element_interactions -->
						<span class="absolute inset-x-2 -bottom-1.5 h-3 cursor-ns-resize touch-none" onpointerdown={(e) => { e.stopPropagation(); editor.down(e, i, 's'); }}>
							<span class="bg-primary absolute inset-x-0 top-1 h-1 rounded-full"></span></span>
						<!-- svelte-ignore a11y_no_static_element_interactions -->
						<span class="bg-primary border-base-100 absolute -right-1.5 -bottom-1.5 size-3 cursor-nwse-resize touch-none rounded-full border-2" onpointerdown={(e) => { e.stopPropagation(); editor.down(e, i, 'se'); }}></span>
					{/if}
				</div>
			{/if}
		</div>
	{/each}
</div>
