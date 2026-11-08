<script lang="ts">
	import Icon from '../Icon.svelte';
	import { api } from '../api.ts';
	import IntegrationDialog from './IntegrationDialog.svelte';
	import PickerRow from './PickerRow.svelte';
	import type { Integration } from './types.ts';

	/** "Add device" for the Devices page: the integrations you have that can add devices (a search, pairing), and the
	 * same dialog the Integrations page uses for each. The server pushes the new devices over the live connection. */
	let items = $state<Integration[]>([]);
	let picking = $state(false);
	let chosen = $state<string | null>(null);
	const chosenItem = $derived(items.find((i) => i.id === chosen) ?? null);
	const eligible = $derived(items.filter((i) => i.added && !i.always && i.can_add));

	async function open() {
		items = await api<Integration[]>('/integrations'); // read when the button is pressed, not on a timer
		picking = true;
	}
	const replace = (updated: Integration) => (items = items.map((i) => (i.id === updated.id ? updated : i)));
</script>

<button class="btn btn-sm btn-primary" onclick={open}><Icon name="plus" class="size-4" />Add device</button>

{#if picking}
	<div class="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
		<button class="absolute inset-0 bg-black/50" aria-label="Close" onclick={() => (picking = false)}></button>
		<div class="bg-base-100 relative flex max-h-[85dvh] w-full max-w-xl flex-col gap-2 overflow-hidden rounded-t-2xl p-4 pb-6 sm:rounded-2xl">
			<div class="flex shrink-0 items-center">
				<h2 class="grow text-lg font-bold">Add a device</h2>
				<button class="btn btn-ghost btn-sm btn-circle" aria-label="Close" onclick={() => (picking = false)}><Icon name="close" class="size-5" /></button>
			</div>
			<div class="flex min-h-0 flex-col gap-2 overflow-x-hidden overflow-y-auto">
				{#each eligible as item (item.id)}
					<PickerRow {item} text={item.searchable ? `Search for ${item.noun ?? 'devices'}` : item.add_text || 'Add a device'} onclick={() => { chosen = item.id; picking = false; }} />
				{:else}
					<p class="py-6 text-center text-sm opacity-70">
						None of your integrations can add devices from here yet. <a class="link" href="/integrations">Add an integration</a> first.
					</p>
				{/each}
			</div>
		</div>
	</div>
{/if}

{#if chosenItem}
	<IntegrationDialog item={chosenItem} isNew={false} devicesOnly onchange={replace} ondone={() => (chosen = null)} oncancel={() => (chosen = null)} />
{/if}
