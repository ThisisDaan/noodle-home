<script lang="ts">
	import Icon from '#lib/Icon.svelte';
	import { api } from '#lib/api.ts';
	import IntegrationForm from '#lib/integrations/IntegrationForm.svelte';
	import { dot, type Integration } from '#lib/integrations/types.ts';

	let items = $state<Integration[]>([]);
	let loaded = $state(false);
	let open = $state<string | null>(null); // the integration whose settings are showing
	let picker = $state(false);

	// The integration being set up in the dialog. It only joins the list once it is connected or has a device.
	let draftId = $state<string | null>(null);
	const draft = $derived(items.find((i) => i.id === draftId) ?? null);
	const added = $derived(items.filter((i) => i.added && !i.always && i.id !== draftId));
	const available = $derived(items.filter((i) => !i.added && !i.always));

	$effect(() => {
		api<Integration[]>('/integrations').then((list) => {
			items = list;
			loaded = true;
		});
	});

	const replace = (updated: Integration) => (items = items.map((i) => (i.id === updated.id ? updated : i)));

	async function add(item: Integration) {
		picker = false;
		draftId = item.id;
		replace(await api<Integration>(`/integrations/${item.id}/add`, { body: {} }));
	}

	// Something is connected: the service answers, or a device was found, paired or added.
	const ready = (i: Integration) =>
		i.connected === true || !!(i.devices?.length || i.bulbs?.length || i.sensors?.length || i.paired) || (!i.searchable && !i.panel);

	// Settings to fill in: the dialog then has Cancel and Save. Otherwise (search, pairing) it has Cancel and Done.
	const hasFields = (i: Integration) => !i.custom_form && i.fields.some((f) => !f.hidden && !f.advanced);

	async function finish() {
		const id = draftId;
		draftId = null;
		open = id;
		setTimeout(() => document.getElementById(`int-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
	}

	async function cancel() {
		const id = draftId;
		draftId = null;
		if (id) replace(await api<Integration>(`/integrations/${id}`, { method: 'DELETE' }));
	}

	const label = (c: boolean | null) => (c === true ? 'Connected' : c === false ? 'Not connected' : 'Set it up');
	const short = (text: string) => text.split('. ')[0].replace(/\.$/, '') + '.';
</script>

<div class="mb-4 flex items-start gap-3">
	<div class="grow">
		<h1 class="text-2xl font-bold">Integrations</h1>
		<p class="text-sm opacity-70">The services your devices live on. Saved on this hub; the same settings are in settings.yaml if you prefer a file.</p>
	</div>
	<button class="btn btn-primary" onclick={() => (picker = true)} disabled={!available.length}><Icon name="plus" class="size-5" />Add</button>
</div>

{#if !loaded}
	<div class="flex justify-center py-20"><span class="loading loading-dots loading-lg text-primary"></span></div>
{:else}
	<div class="flex flex-col gap-3">
		{#each added as item (item.id)}
			<div id="int-{item.id}" class="card bg-base-100 border-base-content/10 border">
				<button class="flex items-center gap-3 p-4 text-left" onclick={() => (open = open === item.id ? null : item.id)} aria-expanded={open === item.id}>
					<span class="icon-bubble size-11"><Icon name={item.icon} class="size-5" /></span>
					<span class="min-w-0 grow">
						<span class="block font-bold">{item.name}</span>
						<span class="flex items-center gap-1.5 text-sm opacity-70"><span class="status {dot(item.connected)}"></span>{label(item.connected)}</span>
					</span>
					<Icon name={open === item.id ? 'up' : 'down'} class="size-5 opacity-60" />
				</button>
				{#if open === item.id}
					<div class="px-4 pb-4"><IntegrationForm {item} onchange={replace} onremove={() => (open = null)} /></div>
				{/if}
			</div>
		{:else}
			<div class="bg-base-100 border-base-content/10 rounded-box border p-8 text-center">
				<p class="font-bold">Nothing connected yet</p>
				<p class="mb-4 text-sm opacity-70">Add the service your devices use: Zigbee, Philips Hue, Matter…</p>
				<button class="btn btn-primary" onclick={() => (picker = true)}><Icon name="plus" class="size-5" />Add integration</button>
			</div>
		{/each}

	</div>
{/if}

{#if picker}
	<div class="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
		<button class="absolute inset-0 bg-black/50" aria-label="Close" onclick={() => (picker = false)}></button>
		<div class="bg-base-100 relative flex max-h-[85dvh] w-full max-w-lg flex-col gap-2 overflow-y-auto rounded-t-2xl p-4 pb-6 sm:rounded-2xl">
			<div class="flex items-center">
				<h2 class="grow text-lg font-bold">Add an integration</h2>
				<button class="btn btn-ghost btn-sm btn-circle" aria-label="Close" onclick={() => (picker = false)}><Icon name="close" class="size-5" /></button>
			</div>
			{#each available as item (item.id)}
				<button class="hover:bg-base-200 rounded-box flex items-center gap-3 p-3 text-left" onclick={() => add(item)}>
					<span class="icon-bubble size-11"><Icon name={item.icon} class="size-5" /></span>
					<span class="min-w-0 grow">
						<span class="block font-bold">{item.name}</span>
						<span class="block text-sm opacity-70">{short(item.help)}</span>
					</span>
					<Icon name="right" class="size-5 opacity-50" />
				</button>
			{/each}
		</div>
	</div>
{/if}

{#if draft}
	<div class="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
		<button class="absolute inset-0 bg-black/50" aria-label="Cancel" onclick={cancel}></button>
		<div class="bg-base-100 relative flex max-h-[90dvh] w-full max-w-lg flex-col gap-3 overflow-y-auto rounded-t-2xl p-4 pb-6 sm:rounded-2xl">
			<div class="flex items-center gap-3">
				<span class="icon-bubble size-11"><Icon name={draft.icon} class="size-5" /></span>
				<h2 class="grow text-lg font-bold">Add {draft.name}</h2>
				<button class="btn btn-ghost btn-sm btn-circle" aria-label="Cancel" onclick={cancel}><Icon name="close" class="size-5" /></button>
			</div>
			<IntegrationForm item={draft} onchange={replace} removable={false} formId="setup-form" hideActions onsaved={finish} />
			<div class="flex items-center justify-end gap-2">
				{#if !hasFields(draft) && !ready(draft)}<span class="grow text-xs opacity-60">It is added to your list once it is connected.</span>{/if}
				<button class="btn" onclick={cancel}>Cancel</button>
				{#if hasFields(draft)}
					<button class="btn btn-primary" type="submit" form="setup-form">Save</button>
				{:else}
					<button class="btn btn-primary" disabled={!ready(draft)} onclick={finish}>Done</button>
				{/if}
			</div>
		</div>
	</div>
{/if}
