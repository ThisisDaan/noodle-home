<script lang="ts">
	import { api } from '../api.ts';
	import Discover from './Discover.svelte';
	import type { Integration, PanelProps } from './types.ts';

	let { item, onchange }: PanelProps = $props();
	let busy = $state(false);
	let error = $state('');

	async function remove(mac: string) {
		busy = true;
		error = '';
		try {
			onchange(await api<Integration>(`/lifx/bulbs/${encodeURIComponent(mac)}`, { method: 'DELETE' }));
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}
</script>

{#if item.bulbs?.length}
	<div class="flex flex-col gap-1">
		<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">Your bulbs</h3>
		{#each item.bulbs as bulb (bulb.mac)}
			<div class="bg-base-200 rounded-box flex items-center gap-3 p-3">
				<span class="status {bulb.available ? 'status-success' : 'status-warning'}"></span>
				<span class="min-w-0 grow"><span class="block truncate font-medium">{bulb.name}</span>
					<span class="block truncate text-xs opacity-60">{bulb.address}</span></span>
				<button type="button" class="btn btn-ghost btn-sm text-error" disabled={busy} onclick={() => remove(bulb.mac)}>Remove</button>
			</div>
		{/each}
	</div>
{/if}
<Discover id="lifx" initial={item.search} noun="LIFX bulbs" {onchange} />
{#if error}<div role="alert" class="alert alert-error alert-soft text-sm">{error}</div>{/if}
