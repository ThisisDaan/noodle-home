<script lang="ts">
	import { api } from '../api.ts';
	import type { Integration, PanelProps } from './types.ts';

	type Nearby = { address: string; name: string; rssi: number | null; kind: string | null; added: boolean };

	let { item, onchange }: PanelProps = $props();
	let busy = $state(false);
	let error = $state('');
	let nearby = $state<{ scanning: boolean; error: string | null; devices: Nearby[] }>({ scanning: false, error: null, devices: [] });

	// While this panel is showing, keep looking at what is nearby.
	$effect(() => {
		const look = () => api<typeof nearby>('/ble/nearby').then((r) => (nearby = r)).catch(() => {});
		look();
		const timer = setInterval(look, 3000);
		return () => clearInterval(timer);
	});
	const sensors = $derived(nearby.devices.filter((d) => d.kind && !d.added));
	const others = $derived(nearby.devices.filter((d) => !d.kind).length);

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
	const add = (d: Nearby) =>
		change(() => api<Integration>('/ble/sensors', { body: { address: d.address, name: d.name || d.kind || d.address } }));
	const remove = (address: string) =>
		change(() => api<Integration>(`/ble/sensors/${encodeURIComponent(address)}`, { method: 'DELETE' }));
</script>

{#if item.sensors?.length}
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
<div class="flex flex-col gap-1">
	<h3 class="flex items-center gap-2 text-xs font-semibold tracking-wide uppercase opacity-60">
		Nearby {#if nearby.scanning}<span class="loading loading-dots loading-xs"></span>{/if}
	</h3>
	{#if nearby.error}
		<div role="alert" class="alert alert-error alert-soft text-sm">Bluetooth is not available on this machine: {nearby.error}</div>
	{:else}
		{#each sensors as d (d.address)}
			<div class="bg-base-200 rounded-box flex items-center gap-3 p-3">
				<span class="min-w-0 grow"><span class="block truncate font-medium">{d.name || d.kind}</span>
					<span class="block truncate text-xs opacity-60">{d.kind} · {d.address} · {d.rssi ?? '?'} dBm</span></span>
				<button type="button" class="btn btn-primary btn-sm" disabled={busy} onclick={() => add(d)}>Add</button>
			</div>
		{:else}
			<p class="text-sm opacity-60">No new sensor heard yet. Put a battery in the sensor or hold it near this machine; it appears here within a few seconds.</p>
		{/each}
		{#if others}<p class="text-xs opacity-50">{others} other Bluetooth device{others > 1 ? 's' : ''} nearby ignored (not a sensor this hub can read).</p>{/if}
	{/if}
</div>
{#if error}<div role="alert" class="alert alert-error alert-soft text-sm">{error}</div>{/if}
