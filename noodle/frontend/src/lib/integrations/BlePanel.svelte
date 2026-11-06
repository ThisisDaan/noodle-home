<script lang="ts">
	import { api } from '../api.ts';
	import type { Integration, PanelProps } from './types.ts';

	let { item, onchange, adding = false }: PanelProps = $props();
	let busy = $state(false);
	let error = $state('');

	async function change(work: () => Promise<Integration>) {
		busy = true;
		error = '';
		try {
			onchange(await work());
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}
	const remove = (address: string) =>
		change(() => api<Integration>(`/ble/sensors/${encodeURIComponent(address)}`, { method: 'DELETE' }));
</script>

{#if !adding && item.sensors?.length}
	<div class="flex flex-col gap-1">
		<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">Your sensors</h3>
		{#each item.sensors as sensor (sensor.address)}
			<div class="bg-base-200 rounded-box flex items-center gap-3 p-3">
				<span class="status {sensor.available ? 'status-success' : 'status-warning'}"></span>
				<span class="min-w-0 grow"><span class="block truncate font-medium">{sensor.name}</span>
					<span class="block truncate text-xs opacity-60">{sensor.model ?? 'Waiting to hear it'} · {sensor.address}</span></span>
				<button type="button" class="btn btn-ghost btn-sm text-error" disabled={busy} onclick={() => remove(sensor.address)}>Remove</button>
			</div>
		{/each}
	</div>
{/if}
{#if error}<div role="alert" class="alert alert-error alert-soft text-sm">{error}</div>{/if}
