<script lang="ts">
	import { formatState, type Device } from '../api.ts';
	import Icon from '../Icon.svelte';
	import { presenceEntity } from './kinds.ts';
	import { agoText, useClock } from './clock.svelte.ts';

	/** Whether someone is there right now (presence, which holds for a few minutes after the last motion). tile: a
	 * status bar on a card, which lights up while someone is there; large: the top of the device sheet, with since when. */
	let { device, size = 'tile' }: { device: Device; size?: 'tile' | 'large' } = $props();

	const clock = useClock();
	const entity = $derived(presenceEntity(device));
	const unknown = $derived(entity?.state === null || entity?.state === undefined);
	// Until the sensor reports again, show what it said last (dimmed) instead of nothing.
	const shown = $derived(entity ? (unknown && entity.last != null ? { ...entity, state: entity.last } : entity) : undefined);
	const active = $derived(device.available && !unknown && entity?.state === true);
</script>

{#if entity}
	{#if size === 'large'}
		<div class="bg-base-200 rounded-box flex flex-col items-center gap-2 p-5 text-center" class:opacity-50={!device.available}>
			<span class="relative grid size-20 place-items-center">
				{#if active}<span class="bg-success/30 absolute inset-0 animate-ping rounded-full"></span>{/if}
				<span class="relative grid size-16 place-items-center rounded-full {active ? 'bg-success text-success-content' : 'bg-base-300 opacity-70'}">
					<Icon name="motion" class="size-8" />
				</span>
			</span>
			<div class="text-2xl font-bold" class:opacity-50={unknown}>{shown ? formatState(shown) : '–'}</div>
			<div class="text-sm opacity-60">{entity.changed ? (entity.state === null ? `last activity ${agoText(entity.changed, clock.now)}` : `since ${agoText(entity.changed, clock.now).replace(' ago', '')}`) : 'no activity recorded yet'}</div>
		</div>
	{:else}
		<div class="rounded-box flex h-12 items-center gap-3 px-4 transition-colors {active ? 'bg-success/20 text-success' : 'bg-base-content/5'}"
			class:opacity-50={!device.available}>
			<span class="relative grid size-3 place-items-center">
				{#if active}<span class="bg-success absolute inline-flex size-5 animate-ping rounded-full opacity-40"></span>{/if}
				<span class="relative size-3 rounded-full {active ? 'bg-success' : 'bg-base-content/30'}"></span>
			</span>
			<span class="font-semibold" class:opacity-60={unknown}>{shown ? formatState(shown) : '–'}</span>
		</div>
	{/if}
{/if}
