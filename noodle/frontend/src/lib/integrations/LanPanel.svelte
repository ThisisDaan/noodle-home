<script lang="ts">
	import { api } from '../api.ts';
	import type { Integration, PanelProps } from './types.ts';

	/** The devices of an integration that is reached by address (Shelly, WLED, Kasa, Nanoleaf, Sonos): the list,
	 * and a way to add one by its IP address. Searching is the Search button of the page. */
	let { item, onchange, adding = false }: PanelProps = $props();
	let busy = $state(false);
	let error = $state('');
	let host = $state('');

	async function run(request: () => Promise<Integration>) {
		busy = true;
		error = '';
		try {
			onchange(await request());
			host = '';
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}

	const add = () => run(() => api<Integration>(`/${item.id}/devices`, { body: { host } }));
	const remove = (key: string) => run(() => api<Integration>(`/${item.id}/devices/${encodeURIComponent(key)}`, { method: 'DELETE' }));
</script>

{#if !adding && item.devices?.length}
	<div class="flex flex-col gap-1">
		<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">Your devices</h3>
		{#each item.devices as d (d.key)}
			<div class="bg-base-200 rounded-box flex items-center gap-3 p-3">
				<span class="status {d.available ? 'status-success' : 'status-warning'}"></span>
				<span class="min-w-0 grow"><span class="block truncate font-medium">{d.name}</span>
					<span class="block truncate text-xs opacity-60">{d.address}</span></span>
				<button type="button" class="btn btn-ghost btn-sm text-error" disabled={busy} onclick={() => remove(d.key)}>Remove</button>
			</div>
		{/each}
	</div>
{/if}
{#if adding}
<form class="flex flex-col gap-1" onsubmit={(e) => { e.preventDefault(); if (host.trim()) add(); }}>
	<label class="floating-label"><span>Add by IP address</span>
		<span class="join w-full">
			<input class="input join-item w-full" placeholder="192.168.1.40" bind:value={host} disabled={busy} />
			<button class="btn btn-primary join-item" disabled={busy || !host.trim()}>Add</button>
		</span></label>
	{#if item.add_hint}<p class="text-xs opacity-60">{item.add_hint}</p>{/if}
</form>
{/if}
{#if error}<div role="alert" class="alert alert-error alert-soft text-sm">{error}</div>{/if}
