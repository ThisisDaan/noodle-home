<script lang="ts">
	import Icon from '../Icon.svelte';
	import SupportBadge from './SupportBadge.svelte';
	import type { Integration } from './types.ts';

	/** One row of the Add dialog: an integration with its icon, name, support badge and a line of text. */
	let { item, text, action = 'right', onclick }: { item: Integration; text: string; action?: 'right' | 'plus'; onclick: () => void } = $props();
</script>

<button class="hover:bg-base-200 rounded-box flex items-center gap-3 p-3 text-left" {onclick}>
	<span class="icon-bubble size-11"><Icon name={item.icon} class="size-5" /></span>
	<span class="min-w-0 grow">
		<span class="flex flex-wrap items-center gap-2 font-bold">{item.name}<SupportBadge support={item.support} /></span>
		<span class="block text-sm opacity-70">{text}</span>
	</span>
	<Icon name={action} class="size-5 opacity-50" />
</button>
