<script lang="ts">
	import { formatState, type Device } from '../api.ts';
	import Icon from '../Icon.svelte';
	import { isMotion } from './kinds.ts';
	import { lastChanges } from './last.svelte.ts';

	/** Whether there is motion (or someone there) right now, and since when. */
	let { device, size = 'tile' }: { device: Device; size?: 'tile' | 'large' } = $props();

	const last = lastChanges(() => device.id);
	const entity = $derived(device.entities.find((e) => isMotion(e) && e.device_class === 'occupancy') ?? device.entities.find(isMotion));
	const active = $derived(device.available && entity?.state === true);
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
			<div class="text-2xl font-bold">{formatState(entity)}</div>
			<div class="text-sm opacity-60">{last.get(entity.key) ? `since ${last.ago(entity.key)}` : 'no activity recorded yet'}</div>
		</div>
	{:else}
		<div class="flex items-center gap-2" class:opacity-50={!device.available}>
			<span class="status {active ? 'status-success' : 'status-neutral'}" class:animate-pulse={active}></span>
			<span class="font-semibold">{formatState(entity)}</span>
			<span class="text-xs opacity-60">{last.ago(entity.key)}</span>
		</div>
	{/if}
{/if}
