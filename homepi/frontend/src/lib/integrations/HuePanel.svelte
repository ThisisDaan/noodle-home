<script lang="ts">
	import Icon from '../Icon.svelte';
	import { api, ApiError } from '../api.ts';
	import { dot, type Integration, type PanelProps } from './types.ts';

	let { item, onchange }: PanelProps = $props();

	// Pairing wizard: start → finding → found → pairing → done (or failed)
	const PAIR_SECONDS = 30;
	type Step = 'start' | 'finding' | 'found' | 'pairing' | 'done' | 'failed';
	let step = $state<Step>('start');
	let host = $state('');
	let bridges = $state<string[]>([]);
	let error = $state('');
	let secondsLeft = $state(PAIR_SECONDS);
	let run = 0; // bumped to cancel a pairing loop that is still waiting
	$effect(() => () => void run++);

	const savedHost = $derived(item.fields.find((f) => f.key === 'hue_host')?.value ?? '');

	async function findBridges() {
		step = 'finding';
		error = '';
		try {
			bridges = (await api<{ bridges: string[] }>('/hue/discover', { body: {} })).bridges;
			if (bridges.length === 1) host = bridges[0];
		} catch (err) {
			bridges = [];
			error = err instanceof Error ? err.message : String(err);
		}
		step = 'found';
	}

	async function startPairing(address: string) {
		host = address.trim();
		if (!host) return;
		const mine = ++run;
		const end = Date.now() + PAIR_SECONDS * 1000;
		step = 'pairing';
		secondsLeft = PAIR_SECONDS;
		error = '';
		while (mine === run) {
			secondsLeft = Math.max(0, Math.ceil((end - Date.now()) / 1000));
			try {
				onchange(await api<Integration>('/hue/pair', { body: { host } }));
				if (mine === run) step = 'done';
				return;
			} catch (err) {
				if (!(err instanceof ApiError && err.status === 409)) {
					if (mine === run) { error = err instanceof Error ? err.message : String(err); step = 'failed'; }
					return;
				}
			}
			if (Date.now() >= end) break;
			await new Promise((r) => setTimeout(r, 1000));
		}
		if (mine === run) { error = 'The button was not pressed in time.'; step = 'failed'; }
	}

	const cancel = () => { run++; step = 'found'; };
</script>

<div class="bg-base-200 rounded-box flex flex-col items-center gap-4 p-5 text-center">
	{#if step === 'start'}
		{#if item.connected !== null}
			<span class="status {dot(item.connected)}"></span>
			<p class="font-medium">{item.connected ? 'Connected to your Hue bridge' : 'Paired, but the bridge is not answering'}</p>
			<p class="text-sm opacity-70">{savedHost}</p>
			<button type="button" class="btn btn-sm" onclick={findBridges}>Pair a different bridge</button>
		{:else}
			<Icon name="bulb" class="size-10 opacity-60" />
			<p class="text-sm opacity-70">Let us look for the Hue bridge on your network.</p>
			<button type="button" class="btn btn-primary" onclick={findBridges}>Find my bridge</button>
		{/if}

	{:else if step === 'finding'}
		<span class="loading loading-ring loading-lg text-primary"></span>
		<p class="font-medium">Looking for your bridge…</p>

	{:else if step === 'found'}
		{#if bridges.length}
			<p class="font-medium">Found {bridges.length} bridge{bridges.length > 1 ? 's' : ''}. Pick yours.</p>
			<div class="flex w-full flex-col gap-2">
				{#each bridges as ip (ip)}
					<button type="button" class="btn btn-lg justify-start active:scale-95 {host === ip ? 'btn-primary' : 'btn-outline'}" onclick={() => (host = ip)}>
						<Icon name={host === ip ? 'check' : 'bulb'} class="size-5" />Hue bridge · {ip}
					</button>
				{/each}
			</div>
		{:else}
			<p class="font-medium">No bridge found</p>
			<p class="text-sm opacity-70">{error || 'Type its address instead. It is in the Hue app under Settings, Bridges.'}</p>
		{/if}
		<input class="input w-full" bind:value={host} placeholder="Or type its address, e.g. 192.168.1.20" autocomplete="off" />
		<div class="flex w-full justify-between gap-2">
			<button type="button" class="btn btn-ghost btn-sm" onclick={findBridges}>Search again</button>
			<button type="button" class="btn btn-primary" disabled={!host.trim()} onclick={() => startPairing(host)}>Continue</button>
		</div>

	{:else if step === 'pairing'}
		<p class="font-medium">Press the round button on top of your Hue bridge</p>
		<div class="relative grid size-28 place-items-center">
			<span class="bg-primary/40 absolute inline-flex size-24 animate-ping rounded-full"></span>
			<span class="bg-primary/20 absolute inline-flex size-28 animate-pulse rounded-full"></span>
			<span class="bg-primary text-primary-content relative grid size-20 place-items-center rounded-full text-sm font-bold">Press</span>
		</div>
		<div class="flex w-full flex-col gap-1">
			<progress class="progress progress-primary w-full" value={PAIR_SECONDS - secondsLeft} max={PAIR_SECONDS}></progress>
			<p class="text-xs opacity-60">Waiting for the button… {secondsLeft}s left</p>
		</div>
		<button type="button" class="btn btn-ghost btn-sm" onclick={cancel}>Cancel</button>

	{:else if step === 'done'}
		<span class="bg-success text-success-content grid size-16 place-items-center rounded-full"><Icon name="check" class="size-9" /></span>
		<p class="text-lg font-bold">Pairing successful</p>
		<p class="text-sm opacity-70">Your Hue lights will show up in a moment.</p>
		<button type="button" class="btn btn-primary" onclick={() => (step = 'start')}>Done</button>

	{:else}
		<span class="bg-error text-error-content grid size-16 place-items-center rounded-full"><Icon name="close" class="size-9" /></span>
		<p class="text-lg font-bold">Pairing did not work</p>
		<p class="text-sm opacity-70">{error}</p>
		<div class="flex gap-2">
			<button type="button" class="btn btn-ghost btn-sm" onclick={() => (step = 'found')}>Back</button>
			<button type="button" class="btn btn-primary btn-sm" onclick={() => startPairing(host)}>Try again</button>
		</div>
	{/if}
</div>
