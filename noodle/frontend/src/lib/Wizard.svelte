<script lang="ts">
	import Icon from './Icon.svelte';
	import Logo from './Logo.svelte';
	import { api } from './api.ts';
	import IntegrationForm from './integrations/IntegrationForm.svelte';
	import LocationPanel from './integrations/LocationPanel.svelte';
	import type { Integration } from './integrations/types.ts';

	let { onfinish }: { onfinish: () => void } = $props();

	const STEPS = [
		{ id: 'welcome', title: 'Welcome' },
		{ id: 'location', title: 'Your home' },
		{ id: 'services', title: 'Services' },
		{ id: 'connect', title: 'Integrations' },
		{ id: 'device', title: 'First device' }
	] as const;

	let index = $state(0);
	let items = $state<Integration[]>([]);
	let loaded = $state(false);
	let busy = $state(false);
	let error = $state('');
	let pairing = $state<{ ok: boolean; text: string } | null>(null);

	const step = $derived(STEPS[index].id);
	const hub = $derived(items.find((i) => i.always));
	const choices = $derived(items.filter((i) => !i.always));
	const added = $derived(choices.filter((i) => i.added));
	const field = (key: string) => hub?.fields.find((f) => f.key === key)?.value ?? '';

	let homeName = $state('');
	let place = $state({ latitude: '', longitude: '', timezone: '' });

	$effect(() => {
		api<Integration[]>('/integrations').then((list) => {
			items = list;
			const system = list.find((i) => i.always);
			const get = (key: string) => system?.fields.find((f) => f.key === key)?.value ?? '';
			homeName = get('home_name');
			place = { latitude: get('latitude'), longitude: get('longitude'), timezone: get('timezone') };
			loaded = true;
		});
	});

	const replace = (updated: Integration) => {
		items = items.map((i) => (i.id === updated.id ? updated : i));
		if (updated.always) place = { latitude: field('latitude'), longitude: field('longitude'), timezone: field('timezone') };
	};

	/** Keep what was typed on this step, then go on. */
	async function next() {
		error = '';
		busy = true;
		try {
			if (step === 'welcome' && hub && homeName.trim() !== field('home_name')) {
				replace(await api<Integration>('/integrations/system', { method: 'PUT', body: { values: { home_name: homeName.trim() } } }));
			}
			if (step === 'location' && hub) {
				const values = Object.fromEntries(Object.entries(place).filter(([k, v]) => v.trim() !== field(k)));
				if (Object.keys(values).length) {
					replace(await api<Integration>('/integrations/system', { method: 'PUT', body: { values } }));
				}
			}
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

	async function permitJoin() {
		pairing = null;
		try {
			await api('/zigbee/permit_join', { body: { seconds: 60 } });
			pairing = { ok: true, text: 'Open for 60 seconds. Put your Zigbee device in pairing mode now; it shows up under Devices.' };
		} catch (err) {
			pairing = { ok: false, text: err instanceof Error ? err.message : String(err) };
		}
	}

	const short = (text: string) => text.split('. ')[0].replace(/\.$/, '') + '.';
</script>

<div class="bg-base-200 fixed inset-0 z-50 overflow-y-auto">
	<div class="mx-auto flex min-h-full max-w-xl flex-col gap-4 p-4 pb-10 sm:justify-center">
		<div class="flex items-center gap-3">
			<Logo class="size-10" />
			<ol class="flex grow items-center gap-1.5" aria-label="Progress">
				{#each STEPS as s, i (s.id)}
					<li class="h-1.5 grow rounded-full {i <= index ? 'bg-primary' : 'bg-base-content/15'}" aria-current={i === index ? 'step' : undefined}></li>
				{/each}
			</ol>
			<button class="btn btn-ghost btn-sm" onclick={() => finish().catch((e) => (error = String(e)))}>Skip setup</button>
		</div>

		<div class="card bg-base-100 border-base-content/10 border shadow-xl">
			<div class="card-body gap-4">
				{#if !loaded}
					<div class="flex justify-center py-10"><span class="loading loading-dots loading-lg text-primary"></span></div>

				{:else if step === 'welcome'}
					<h1 class="text-2xl font-bold">Welcome to Noodle</h1>
					<p class="opacity-70">A few quick steps to make this hub yours. You can skip any of them and change everything later.</p>
					<label class="floating-label"><span>What do you call your home?</span>
						<input class="input w-full" bind:value={homeName} placeholder="What do you call your home?" autocomplete="off" /></label>

				{:else if step === 'location'}
					<h1 class="text-2xl font-bold">Where is your home?</h1>
					<p class="text-sm opacity-70">Used for sunrise and sunset ("turn the lights on at sunset") and to tell when a phone is home.</p>
					{#if hub}<LocationPanel item={hub} onchange={replace} />{/if}
					<div class="grid grid-cols-2 gap-3">
						<label class="floating-label"><span>Latitude</span>
							<input class="input w-full" bind:value={place.latitude} placeholder="Latitude" inputmode="decimal" autocomplete="off" /></label>
						<label class="floating-label"><span>Longitude</span>
							<input class="input w-full" bind:value={place.longitude} placeholder="Longitude" inputmode="decimal" autocomplete="off" /></label>
					</div>
					<label class="floating-label"><span>Time zone</span>
						<input class="input w-full" bind:value={place.timezone} placeholder="Time zone, e.g. Europe/Amsterdam" autocomplete="off" /></label>

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
									<span class="text-success flex items-center gap-1 text-sm font-medium"><Icon name="check" class="size-4" />Added</span>
								{:else}
									<button class="btn btn-sm btn-primary" disabled={busy} onclick={() => add(item)}>Add</button>
								{/if}
							</div>
						{/each}
					</div>

				{:else if step === 'connect'}
					<h1 class="text-2xl font-bold">Connect them</h1>
					{#if added.length}
						<p class="text-sm opacity-70">Fill in each one. A green dot means it found the service.</p>
						<div class="flex flex-col gap-3">
							{#each added as item (item.id)}
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
					<h1 class="text-2xl font-bold">Add your first device</h1>
					{#if added.some((i) => i.id === 'zigbee')}
						<p class="text-sm opacity-70">For a Zigbee device: start pairing here, then put the device in pairing mode (see its manual, often holding a button for 5 seconds).</p>
						<button class="btn btn-primary w-fit" onclick={permitJoin}>Pair a Zigbee device (60s)</button>
						{#if pairing}<div role="alert" class="alert alert-soft text-sm {pairing.ok ? 'alert-success' : 'alert-error'}">{pairing.text}</div>{/if}
					{/if}
					<p class="text-sm opacity-70">Matter devices are added on the System page with their setup code, and Hue lights appear by themselves once the bridge is paired. Everything shows up under Devices.</p>
				{/if}

				{#if error}<div role="alert" class="alert alert-error alert-soft text-sm">{error}</div>{/if}

				<div class="flex items-center justify-between gap-2 pt-2">
					<button class="btn btn-ghost" disabled={index === 0 || busy} onclick={() => index--}>Back</button>
					<button class="btn btn-primary" disabled={busy || !loaded} onclick={next}>
						{#if busy}<span class="loading loading-spinner loading-sm"></span>{/if}
						{index === STEPS.length - 1 ? 'Finish' : 'Next'}
					</button>
				</div>
			</div>
		</div>
	</div>
</div>
