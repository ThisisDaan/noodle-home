<script lang="ts">
	import { api } from '../api.ts';
	import { live } from '../live.svelte.ts';

	/** Zigbee screen of the first-run wizard: the address of Mosquitto (the MQTT broker) and its port. A search
	 * runs once when the screen opens, for 20 seconds, and fills in the first broker it finds (the server pushes
	 * what it finds; nothing is polled). The wizard's footer button calls `connect`. */
	let { checking = $bindable(false), busy = $bindable(false) }: { checking?: boolean; busy?: boolean } = $props();

	type Setup = { host: string; port: number; connected: boolean; online: boolean; version: string | null };
	type Hit = { key: string; host?: string };
	const SEARCH_ID = 'zigbee-broker';

	let setup = $state<Setup | null>(null);
	let host = $state('');
	let port = $state('1883'); // the standard Mosquitto port
	let typed = $state(false); // once the user typed, a search result no longer overwrites the field
	let error = $state('');

	const search = $derived(live.discovery[SEARCH_ID]);
	const found = $derived((search?.found ?? []) as Hit[]);
	const others = $derived(found.filter((f) => f.host && f.host !== host));

	$effect(() => {
		if (!typed && !host && found.length) host = found[0].host ?? '';
	});

	const message = (err: unknown) => (err instanceof Error ? err.message : String(err));

	$effect(() => {
		api('/zigbee/broker/search', { body: {} }).catch((err) => (error = message(err)));
		return () => void api('/zigbee/broker/search', { method: 'DELETE' }).catch(() => {});
	});

	export async function connect() {
		busy = true;
		error = '';
		try {
			setup = await api<Setup>('/zigbee/broker/use', { body: { host: host.trim(), port: Number(port) || 1883 } });
			checking = true;
		} catch (err) {
			error = message(err);
		} finally {
			busy = false;
		}
	}

	async function recheck() {
		busy = true;
		try {
			setup = await api<Setup>('/zigbee/setup');
		} catch (err) {
			error = message(err);
		} finally {
			busy = false;
		}
	}
</script>

<div class="flex flex-col gap-4">
	<h1 class="text-2xl font-bold">Connect Zigbee</h1>

	{#if !checking}
		<form onsubmit={(e) => { e.preventDefault(); connect(); }}>
			<div class="flex gap-2">
				<label class="floating-label grow"><span>Mosquitto address</span>
					<input class="input w-full" bind:value={host} oninput={() => (typed = true)} placeholder="Mosquitto address, e.g. 192.168.1.20" autocomplete="off" /></label>
				<label class="floating-label w-28 shrink-0"><span>Port</span>
					<input class="input w-full" bind:value={port} inputmode="numeric" placeholder="Port" autocomplete="off" /></label>
			</div>
			<button type="submit" class="sr-only" tabindex="-1">Connect</button>
		</form>
		{#if search?.searching}
			<p class="flex items-center gap-2 text-sm opacity-70" role="status"><span class="loading loading-ring loading-xs"></span>Looking on your network…</p>
		{:else if others.length}
			<p class="text-sm opacity-70">
				Also found:
				{#each others as f, i (f.key)}{i ? ', ' : ''}<button type="button" class="link" onclick={() => { host = f.host ?? ''; typed = true; }}>{f.host}</button>{/each}
			</p>
		{/if}
	{:else}
		<ul class="flex flex-col gap-2">
			<li class="bg-base-200 rounded-box flex items-center gap-3 p-3">
				<span class="status status-success"></span>
				<span class="grow text-sm">Mosquitto at {setup?.host}:{setup?.port}</span>
			</li>
			<li class="bg-base-200 rounded-box flex items-center gap-3 p-3">
				<span class="status {setup?.online ? 'status-success' : 'status-warning'}"></span>
				<span class="grow text-sm">{setup?.online ? `Zigbee2MQTT ${setup.version ?? ''}` : 'Zigbee2MQTT is not answering yet'}</span>
				{#if !setup?.online}<button type="button" class="btn btn-ghost btn-xs" disabled={busy} onclick={recheck}>Check again</button>{/if}
			</li>
		</ul>
	{/if}

	{#if error}<div role="alert" class="alert alert-error alert-soft text-sm">{error}</div>{/if}
</div>
