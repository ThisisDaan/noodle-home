<script lang="ts">
	import Icon from '../Icon.svelte';
	import IntegrationForm from './IntegrationForm.svelte';
	import SupportBadge from './SupportBadge.svelte';
	import type { Integration } from './types.ts';

	/** The dialog for setting up an integration or adding devices to it: its search and pairing, and its settings.
	 * Used by the Integrations page (Add) and the Devices page (Add device). `isNew`: the integration was just added,
	 * so the page removes it again on Cancel; otherwise closing only closes. */
	let { item, isNew, devicesOnly = false, onchange, ondone, oncancel }: {
		item: Integration;
		isNew: boolean;
		/** Adding devices from the Devices page: no settings or status, only how to add. */
		devicesOnly?: boolean;
		onchange: (updated: Integration) => void;
		ondone: () => void;
		oncancel: () => void;
	} = $props();

	// Something is connected: the service answers, or a device was found, paired or added.
	const ready = $derived(
		devicesOnly || item.connected === true || !!(item.devices?.length || item.bulbs?.length || item.sensors?.length || item.paired) || (!item.searchable && !item.panel)
	);
	// Settings to fill in: the dialog then has Cancel and Save. Otherwise (search, pairing) it has Cancel and Done.
	const hasFields = $derived(!devicesOnly && item.fields.some((f) => !f.hidden && !f.advanced));
</script>

<div class="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
	<button class="absolute inset-0 bg-black/50" aria-label="Cancel" onclick={oncancel}></button>
	<div class="bg-base-100 relative flex max-h-[90dvh] w-full max-w-2xl flex-col gap-3 overflow-hidden rounded-t-2xl p-4 pb-6 sm:rounded-2xl">
		<div class="flex shrink-0 items-center gap-3">
			<span class="icon-bubble size-11"><Icon name={item.icon} class="size-5" /></span>
			<h2 class="flex grow flex-wrap items-center gap-2 text-lg font-bold">{isNew ? 'Add' : devicesOnly ? 'Add a device to' : 'Add to'} {item.name}<SupportBadge support={item.support} /></h2>
			<button class="btn btn-ghost btn-sm btn-circle" aria-label="Cancel" onclick={oncancel}><Icon name="close" class="size-5" /></button>
		</div>
		<div class="min-h-0 overflow-x-hidden overflow-y-auto">
			<IntegrationForm {item} {onchange} removable={false} formId="setup-form" hideActions onsaved={ondone} {devicesOnly} />
		</div>
		<div class="flex shrink-0 items-center justify-end gap-2">
			{#if !hasFields && !ready}<span class="grow text-xs opacity-60">It is added to your list once it is connected.</span>{/if}
			<button class="btn" onclick={oncancel}>Cancel</button>
			{#if hasFields}
				<button class="btn btn-primary" type="submit" form="setup-form">Save</button>
			{:else}
				<button class="btn btn-primary" disabled={!ready} onclick={ondone}>Done</button>
			{/if}
		</div>
	</div>
</div>
