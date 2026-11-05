<script lang="ts">
	import { api } from '../api.ts';
	import type { PanelProps } from './types.ts';

	/** The Matter server and the Thread border router, and adding a Matter device with its setup code. */
	let {}: PanelProps = $props();

	type Info = {
		connected: boolean; sdk_version?: string; bluetooth_enabled?: boolean;
		thread: { reachable: boolean; state?: string; network_name?: string; channel?: number; routers?: number };
	};
	let info = $state<Info | null>(null);
	let code = $state('');
	let pairing = $state(false);
	let result = $state('');

	// Asked once when the panel opens (the hub does not push this).
	$effect(() => {
		api<{ matter?: Info }>('/system').then((s) => (info = s.matter ?? null)).catch(() => {});
	});

	async function pair(e: SubmitEvent) {
		e.preventDefault();
		pairing = true;
		result = 'Pairing… keep the device close to the hub.';
		try {
			const res = await api<{ device_id: string }>('/matter/commission', { body: { code } });
			result = `Paired as ${res.device_id}. Give it a name and room under Devices.`;
			code = '';
		} catch (err) {
			result = err instanceof Error ? err.message : String(err);
		} finally {
			pairing = false;
		}
	}
</script>

<div class="flex flex-col gap-3">
	<div class="bg-base-200 rounded-box flex flex-col gap-1 p-3 text-sm">
		<span class="flex items-center gap-2">
			<span class="status {info?.connected ? 'status-success' : info ? 'status-error' : 'status-neutral'}"></span>
			{#if !info}Checking…{:else if info.connected}Matter server running · SDK {info.sdk_version}{:else}Matter server not reachable{/if}
		</span>
		{#if info}
			<span class="flex items-center gap-2">
				<span class="status {info.thread.reachable && info.thread.state === 'leader' ? 'status-success' : info.thread.reachable ? 'status-warning' : 'status-error'}"></span>
				{#if info.thread.reachable}Thread: {info.thread.network_name} · channel {info.thread.channel} · {info.thread.state} · {info.thread.routers} routers
				{:else}Thread border router not reachable{/if}
			</span>
		{/if}
	</div>

	{#if info?.bluetooth_enabled}
		<form class="flex flex-col gap-2" onsubmit={pair}>
			<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">Add a Matter device</h3>
			<div class="join w-full">
				<input class="input input-sm join-item grow" placeholder="QR text (MT:…) or 11-digit code" bind:value={code} disabled={pairing} />
				<button class="btn btn-sm btn-primary join-item" disabled={pairing || code.length < 11}>
					{#if pairing}<span class="loading loading-spinner loading-xs"></span>{/if}Pair
				</button>
			</div>
			<p class="text-xs opacity-60">Hold the device within a few metres of the hub. Pairing takes up to a few minutes.</p>
			{#if result}<p class="text-xs" class:text-error={result.startsWith('Pairing failed')}>{result}</p>{/if}
		</form>
	{:else if info}
		<p class="text-sm opacity-70">Bluetooth pairing is off in the Matter server, so new devices cannot be added from here.</p>
	{/if}
</div>
