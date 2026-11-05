<script lang="ts">
	import { api } from '../api.ts';
	import type { Integration, PanelProps } from './types.ts';

	/** Pairing with an IKEA DIRIGERA hub: enter its address, press Connect, press the action button on the hub,
	 * press Connect again. */
	let { item, onchange }: PanelProps = $props();
	let host = $state('');
	let busy = $state(false);
	let error = $state('');
	let waiting = $state(false);

	async function connect() {
		busy = true;
		error = '';
		try {
			const result = await api<Integration & { paired_now: boolean }>('/dirigera/pair', { body: { host } });
			waiting = !result.paired_now;
			onchange(result);
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
			waiting = false;
		} finally {
			busy = false;
		}
	}
</script>

{#if item.paired}
	<p class="text-sm">Connected to the hub at <b>{item.address}</b>.{#if item.error} <span class="text-error">{item.error}</span>{/if}</p>
{:else}
	<form class="flex flex-col gap-2" onsubmit={(e) => { e.preventDefault(); if (host.trim()) connect(); }}>
		<label class="floating-label"><span>Hub IP address</span>
			<input class="input w-full" placeholder="192.168.1.30" bind:value={host} disabled={busy} /></label>
		{#if waiting}
			<div role="alert" class="alert alert-info alert-soft text-sm">
				Now press the action button on the bottom of the DIRIGERA hub (within a minute), then press Connect again.
			</div>
		{/if}
		<button class="btn btn-primary self-start" disabled={busy || !host.trim()}>{waiting ? 'Connect again' : 'Connect'}</button>
	</form>
{/if}
{#if error}<div role="alert" class="alert alert-error alert-soft text-sm">{error}</div>{/if}
