<script lang="ts">
	import type { Snippet } from 'svelte';

	/** The frame of every setup screen: the first-run wizard and the dialogs that add an integration or a device.
	 * The header stays at the top and the buttons stay in view at the bottom, however long the content gets;
	 * only the content in between scrolls. Give it a bounded height (a max-h, or a flex parent with min-h-0). */
	let { header, children, footer, class: klass = '' }: {
		header?: Snippet;
		children: Snippet;
		/** The buttons (Back / Next, Cancel / Save) and anything that must stay visible with them, like an error. */
		footer: Snippet;
		class?: string;
	} = $props();
</script>

<div class="flex min-h-0 flex-col gap-3 {klass}">
	{#if header}<div class="shrink-0">{@render header()}</div>{/if}
	<!-- px/-mx: room for focus rings, which overflow clipping would cut off -->
	<div class="-mx-1 min-h-0 grow overflow-x-hidden overflow-y-auto overscroll-contain px-1">{@render children()}</div>
	<div class="border-base-content/10 shrink-0 border-t pt-3">{@render footer()}</div>
</div>
