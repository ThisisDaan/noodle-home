<script lang="ts">
	import { type Device } from '../api.ts';
	import Icon from '../Icon.svelte';
	import { agoText, useClock } from './clock.svelte.ts';
	import { contactEntity } from './kinds.ts';

	/** Whether a door, window or mailbox is open right now. Like the motion card: tile is a status bar that lights up
	 * while it is open; large is the top of the device sheet, with since when. */
	let { device, size = 'tile' }: { device: Device; size?: 'tile' | 'large' } = $props();

	const clock = useClock();
	const entity = $derived(contactEntity(device));
	const unknown = $derived(entity?.state === null || entity?.state === undefined);
	const open = $derived(device.available && !unknown && entity?.state === true);
	const word = $derived(unknown ? '–' : entity?.state ? 'Open' : 'Closed');
</script>

{#if entity}
	{#if size === 'large'}
		<div class="bg-base-200 rounded-box flex flex-col items-center gap-2 p-5 text-center" class:opacity-50={!device.available}>
			<span class="grid size-16 place-items-center rounded-full {open ? 'bg-warning text-warning-content' : 'bg-base-300 opacity-70'}">
				<Icon name="door" class="size-8" />
			</span>
			<div class="text-2xl font-bold" class:opacity-50={unknown}>{word}</div>
			<div class="text-sm opacity-60">{entity.changed ? `since ${agoText(entity.changed, clock.now).replace(' ago', '')}` : 'no change recorded yet'}</div>
		</div>
	{:else}
		<div class="rounded-box flex h-12 items-center gap-3 px-4 transition-colors {open ? 'bg-warning/20 text-warning' : 'bg-base-content/5'}"
			class:opacity-50={!device.available}>
			<Icon name="door" class="size-5 shrink-0 {open ? '' : 'opacity-40'}" />
			<span class="font-semibold" class:opacity-60={unknown}>{word}</span>
		</div>
	{/if}
{/if}
