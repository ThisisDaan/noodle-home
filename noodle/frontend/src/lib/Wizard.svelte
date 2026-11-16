<script lang="ts">
	import Icon from './Icon.svelte';
	import Logo from './Logo.svelte';
	import SetupFrame from './SetupFrame.svelte';
	import { api } from './api.ts';
	import { live } from './live.svelte.ts';
	import Discover from './integrations/Discover.svelte';
	import IntegrationForm from './integrations/IntegrationForm.svelte';
	import LocationPanel from './integrations/LocationPanel.svelte';
	import ZigbeeSetup from './integrations/ZigbeeSetup.svelte';
	import type { Integration } from './integrations/types.ts';

	let { onfinish }: { onfinish: () => void } = $props();

	const BASE = [
		{ id: 'welcome', title: 'Welcome' },
		{ id: 'location', title: 'Your home' },
		{ id: 'services', title: 'Services' },
		{ id: 'zigbee', title: 'Zigbee' },
		{ id: 'connect', title: 'Integrations' },
		{ id: 'device', title: 'First device' }
	] as const;

	let index = $state(0);
	let items = $state<Integration[]>([]);
	// The Zigbee screens only exist when Zigbee was added: finding its MQTT broker comes before the rest.
	// "Connect them" only exists when a service other than Zigbee was added (Zigbee has its own screen).
	const STEPS = $derived(
		BASE.filter(
			(s) =>
				(s.id !== 'zigbee' || items.some((i) => i.id === 'zigbee' && i.added)) &&
				(s.id !== 'connect' || items.some((i) => i.added && !i.always && i.id !== 'zigbee'))
		)
	);
	let zig = $state<ZigbeeSetup>();
	let zigChecking = $state(false); // the Zigbee screen got past Connect
	let zigBusy = $state(false);
	let loaded = $state(false);
	let busy = $state(false);
	let error = $state('');

	const step = $derived(STEPS[index]?.id ?? 'device');
	const connecting = $derived(step === 'zigbee' && !zigChecking); // there the footer button says Connect
	$effect(() => {
		if (step !== 'zigbee') zigChecking = false;
	});
	const hub = $derived(items.find((i) => i.always));
	const choices = $derived(items.filter((i) => !i.always));
	const added = $derived(choices.filter((i) => i.added));
	const others = $derived(added.filter((i) => i.id !== 'zigbee'));
	const field = (key: string) => hub?.fields.find((f) => f.key === key)?.value ?? '';

	let homeName = $state('');

	$effect(() => {
		api<Integration[]>('/integrations').then((list) => {
			items = list;
			const system = list.find((i) => i.always);
			const get = (key: string) => system?.fields.find((f) => f.key === key)?.value ?? '';
			homeName = get('home_name');
			loaded = true;
		});
	});

	const replace = (updated: Integration) => {
		items = items.map((i) => (i.id === updated.id ? updated : i));
	};

	/** Keep what was typed on this step, then go on. */
	async function next() {
		error = '';
		busy = true;
		try {
			if (step === 'welcome' && hub && homeName.trim() !== field('home_name')) {
				replace(await api<Integration>('/integrations/system', { method: 'PUT', body: { values: { home_name: homeName.trim() } } }));
			}
			if (step === 'zigbee') items = await api<Integration[]>('/integrations'); // the broker settings changed
			if (index === STEPS.length - 1) await finish();
			else index++;
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}

	async function finish() {
		await api('/setup/finish', { body: {} });
		onfinish();
	}

	async function add(item: Integration) {
		busy = true;
		try {
			replace(await api<Integration>(`/integrations/${item.id}/add`, { body: {} }));
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}

	/** Undo a click on Add (a missed tap). */
	async function remove(item: Integration) {
		busy = true;
		try {
			replace(await api<Integration>(`/integrations/${item.id}`, { method: 'DELETE' }));
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}

	const short = (text: string) => text.split('. ')[0].replace(/\.$/, '') + '.';
</script>

<div class="bg-base-200 fixed inset-0 z-50">
	<div class="mx-auto flex h-full max-w-xl flex-col gap-4 p-4 pb-[max(1rem,env(safe-area-inset-bottom))] sm:justify-center">
		<div class="flex shrink-0 items-center gap-3">
			<Logo class="size-10" />
			<ol class="flex grow items-center gap-1.5" aria-label="Progress">
				{#each STEPS as s, i (s.id)}
					<li class="h-1.5 grow rounded-full {i <= index ? 'bg-primary' : 'bg-base-content/15'}" aria-current={i === index ? 'step' : undefined}></li>
				{/each}
			</ol>
			<button class="btn btn-ghost btn-sm" onclick={() => finish().catch((e) => (error = String(e)))}>Skip setup</button>
		</div>

		<div class="card bg-base-100 border-base-content/10 min-h-0 border shadow-xl">
			<SetupFrame class="card-body gap-4">
				<div class="flex flex-col gap-4">
				{#if !loaded}
					<div class="flex justify-center py-10"><span class="loading loading-dots loading-lg text-primary"></span></div>

				{:else if step === 'welcome'}
					<h1 class="text-2xl font-bold">Welcome to Noodle</h1>
					<p class="opacity-70">A few quick steps to make this hub yours. You can skip any of them and change everything later.</p>
					<label class="floating-label"><span>What do you call your home?</span>
						<input class="input w-full" bind:value={homeName} placeholder="What do you call your home?" autocomplete="off" /></label>

				{:else if step === 'location'}
					<h1 class="text-2xl font-bold">Where is your home?</h1>
					<p class="text-sm opacity-70">Used for sunrise and sunset ("turn the lights on at sunset") and to tell when a phone is home. You can skip this and do it later under System.</p>
					{#if hub}<LocationPanel item={hub} onchange={replace} />{/if}

				{:else if step === 'services'}
					<h1 class="text-2xl font-bold">What do your devices use?</h1>
					<p class="text-sm opacity-70">Add the services you have. Not sure? Skip and add them later under Integrations.</p>
					<div class="flex flex-col gap-2">
						{#each choices as item (item.id)}
							<div class="bg-base-200 rounded-box flex items-center gap-3 p-3">
								<span class="icon-bubble size-11"><Icon name={item.icon} class="size-5" /></span>
								<span class="min-w-0 grow">
									<span class="block font-bold">{item.name}</span>
									<span class="block text-sm opacity-70">{short(item.help)}</span>
								</span>
								{#if item.added}
									<button class="btn btn-sm btn-outline" disabled={busy} onclick={() => remove(item)}>Undo</button>
								{:else}
									<button class="btn btn-sm btn-primary" disabled={busy} onclick={() => add(item)}>Add</button>
								{/if}
							</div>
						{/each}
					</div>

				{:else if step === 'zigbee'}
					<ZigbeeSetup bind:this={zig} bind:checking={zigChecking} bind:busy={zigBusy} />

				{:else if step === 'connect'}
					<h1 class="text-2xl font-bold">Connect them</h1>
					{#if others.length}
						<p class="text-sm opacity-70">Enter the details for each service below, such as its address. The dot turns green when Noodle can reach it.</p>
						<div class="flex flex-col gap-3">
							{#each others as item (item.id)}
								<div class="border-base-content/10 rounded-box border p-4">
									<div class="mb-2 flex items-center gap-2 font-bold">
										<Icon name={item.icon} class="size-5" />{item.name}
										<span class="status ml-auto {item.connected ? 'status-success' : 'status-neutral'}"></span>
									</div>
									<IntegrationForm {item} onchange={replace} removable={false} />
								</div>
							{/each}
						</div>
					{:else}
						<p class="opacity-70">You haven't added a service yet. You can do that any time under Integrations.</p>
					{/if}

				{:else}
					<h1 class="text-2xl font-bold">Your devices</h1>
					{#each added.filter((i) => i.searchable) as item (item.id)}
						{@const have = live.list.filter((d) => d.source === item.id)}
						<div class="border-base-content/10 rounded-box border p-4">
							<div class="mb-2 flex items-center gap-2 font-bold"><Icon name={item.icon} class="size-5" />{item.name}</div>
							{#if have.length}
								<p class="mb-1 text-sm"><span class="text-success font-medium">{have.length} {have.length === 1 ? 'device' : 'devices'} found</span></p>
								<p class="mb-3 text-sm opacity-70">{have.slice(0, 6).map((d) => d.name).join(', ')}{have.length > 6 ? `, +${have.length - 6} more` : ''}</p>
							{/if}
							<p class="mb-2 text-sm font-medium">Add another</p>
							<Discover {item} onchange={replace} />
						</div>
					{/each}
					{#if added.some((i) => i.id === 'matter')}
						<p class="text-sm opacity-70">Matter devices are added under Integrations › Matter with their setup code.</p>
					{/if}
				{/if}
				</div>

				{#snippet footer()}
					{#if error}<div role="alert" class="alert alert-error alert-soft mb-3 text-sm">{error}</div>{/if}
					<div class="flex items-center justify-between gap-2">
						<button class="btn btn-ghost" disabled={index === 0 || busy} onclick={() => index--}>Back</button>
						<button class="btn btn-primary" disabled={busy || zigBusy || !loaded} onclick={() => (connecting ? zig?.connect() : next())}>
							{#if busy || zigBusy}<span class="loading loading-spinner loading-sm"></span>{/if}
							{index === STEPS.length - 1 ? 'Finish' : connecting ? 'Connect' : 'Next'}
						</button>
					</div>
				{/snippet}
			</SetupFrame>
		</div>
	</div>
</div>
