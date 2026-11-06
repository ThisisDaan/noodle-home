<script lang="ts">
	import { ApiError, api } from '../api.ts';
	import type { Integration, PanelProps } from './types.ts';

	/** The Hue bridges that are paired (more than one is fine): their state, a way to remove one, and a way to add
	 * one by its IP address. Searching is the Search button of the page. */
	let { item, onchange, adding = false }: PanelProps = $props();
	let busy = $state(false);
	let error = $state('');
	let host = $state('');
	let waiting = $state<{ left: number; message: string } | null>(null);
	let attempt = 0; // bumped to cancel a wait that is still running
	$effect(() => () => void attempt++);

	async function remove(address: string) {
		if (!confirm(`Remove the bridge at ${address}? Its lights and sensors disappear from this hub.`)) return;
		busy = true;
		error = '';
		try {
			onchange(await api<Integration>(`/hue/bridges/${encodeURIComponent(address)}`, { method: 'DELETE' }));
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}

	// Pairing needs the round button pressed: the server answers 409 until it was, so ask again each second.
	async function add() {
		const mine = ++attempt;
		const end = Date.now() + 30_000;
		const address = host.trim();
		busy = true;
		error = '';
		try {
			while (mine === attempt) {
				try {
					onchange(await api<Integration>(`/integrations/${item.id}/found/${encodeURIComponent(address)}/add`, { body: {} }));
					host = '';
					waiting = null;
					return;
				} catch (err) {
					if (!(err instanceof ApiError && err.status === 409)) throw err;
					waiting = { left: Math.max(0, Math.ceil((end - Date.now()) / 1000)), message: err.message };
				}
				if (Date.now() >= end) throw new Error('The button was not pressed in time.');
				await new Promise((r) => setTimeout(r, 1000));
			}
		} catch (err) {
			if (mine === attempt) {
				waiting = null;
				error = err instanceof Error ? err.message : String(err);
			}
		} finally {
			if (mine === attempt) busy = false;
		}
	}
	const cancel = () => {
		attempt++;
		waiting = null;
		busy = false;
	};
</script>

{#if !adding && item.bridges?.length}
	<div class="flex flex-col gap-1">
		<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">Your bridges</h3>
		{#each item.bridges as b (b.host)}
			<div class="bg-base-200 rounded-box flex items-center gap-3 p-3">
				<span class="status {b.connected ? 'status-success' : 'status-warning'}"></span>
				<span class="min-w-0 grow"><span class="block truncate font-medium">{b.host}</span>
					<span class="block truncate text-xs opacity-60">{b.connected ? 'Connected' : b.error || 'Connecting…'}</span></span>
				<button type="button" class="btn btn-ghost btn-sm text-error" disabled={busy} onclick={() => remove(b.host)}>Remove</button>
			</div>
		{/each}
	</div>
{/if}
{#if adding}
<form class="flex flex-col gap-1" onsubmit={(e) => { e.preventDefault(); if (host.trim() && !busy) add(); }}>
	<label class="floating-label"><span>Add a bridge by IP address</span>
		<span class="join w-full">
			<input class="input join-item w-full" placeholder="192.168.1.20" bind:value={host} disabled={busy} />
			<button class="btn btn-primary join-item" disabled={busy || !host.trim()}>Add</button>
		</span></label>
</form>
{/if}
{#if waiting}
	<div role="alert" class="alert alert-info alert-soft text-sm">
		<span class="grow">{waiting.message} Waiting… {waiting.left} s</span>
		<button type="button" class="btn btn-ghost btn-xs" onclick={cancel}>Cancel</button>
	</div>
{/if}
{#if error}<div role="alert" class="alert alert-error alert-soft text-sm">{error}</div>{/if}
