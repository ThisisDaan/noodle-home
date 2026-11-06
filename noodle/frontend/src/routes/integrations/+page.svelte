<script lang="ts">
	import Icon from '#lib/Icon.svelte';
	import { api } from '#lib/api.ts';
	import IntegrationDialog from '#lib/integrations/IntegrationDialog.svelte';
	import IntegrationForm from '#lib/integrations/IntegrationForm.svelte';
	import PickerRow from '#lib/integrations/PickerRow.svelte';
	import SupportBadge from '#lib/integrations/SupportBadge.svelte';
	import { dot, type Integration } from '#lib/integrations/types.ts';

	let items = $state<Integration[]>([]);
	let loaded = $state(false);
	let open = $state<string | null>(null); // the integration whose settings are showing
	let picker = $state(false);
	let query = $state('');

	// The integration being set up in the dialog. It only joins the list once it is connected or has a device.
	let draftId = $state<string | null>(null);
	let draftNew = $state(true); // false: more devices for an integration that is already added (Cancel keeps it)
	const draft = $derived(items.find((i) => i.id === draftId) ?? null);
	const added = $derived(items.filter((i) => i.added && !i.always && !(draftNew && i.id === draftId)));
	const available = $derived(items.filter((i) => !i.added && !i.always));
	// The picker's search box: matches the name and the description, every word of what was typed.
	const matches = $derived.by(() => {
		const words = query.toLowerCase().split(/\s+/).filter(Boolean);
		return available.filter((i) => words.every((w) => `${i.name} ${i.help}`.toLowerCase().includes(w)));
	});
	// Integrations that are added and can take another connection (a second Hue bridge): the picker offers it here.
	// Adding devices (bulbs, sensors) is on the Devices page.
	const more = $derived.by(() => {
		const words = query.toLowerCase().split(/\s+/).filter(Boolean);
		return items.filter((i) => i.added && !i.always && i.searchable && i.search_finds === 'connection' && words.every((w) => `${i.name} ${i.help}`.toLowerCase().includes(w)));
	});
	const openPicker = () => {
		query = '';
		picker = true;
	};

	$effect(() => {
		api<Integration[]>('/integrations').then((list) => {
			items = list;
			loaded = true;
		});
	});

	/** Puts the cursor in the search box when the picker opens. */
	const focus = (node: HTMLElement) => node.focus();

	const replace = (updated: Integration) => (items = items.map((i) => (i.id === updated.id ? updated : i)));

	function addMore(item: Integration) {
		picker = false;
		draftNew = false;
		draftId = item.id;
	}

	async function add(item: Integration) {
		picker = false;
		draftNew = true;
		draftId = item.id;
		replace(await api<Integration>(`/integrations/${item.id}/add`, { body: {} }));
	}

	async function finish() {
		const id = draftId;
		draftId = null;
		open = id;
		setTimeout(() => document.getElementById(`int-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
	}

	async function cancel() {
		const id = draftId;
		if (!id) return;
		if (!draftNew) {
			draftId = null; // it was added before: closing only closes the dialog
			return;
		}
		// Mark it not added before the dialog closes, or it shows in the list until the server has answered.
		items = items.map((i) => (i.id === id ? { ...i, added: false } : i));
		draftId = null;
		replace(await api<Integration>(`/integrations/${id}`, { method: 'DELETE' }));
	}

	const label = (c: boolean | null) => (c === true ? 'Connected' : c === false ? 'Not connected' : 'Set it up');
	const short = (text: string) => text.split('. ')[0].replace(/\.$/, '') + '.';
</script>

<div class="mb-1 flex items-center gap-3">
	<h1 class="mr-auto min-w-0 truncate text-3xl font-bold tracking-tight">Integrations</h1>
	<button class="btn btn-sm btn-primary shrink-0" onclick={openPicker} disabled={!available.length && !more.length}><Icon name="plus" class="size-4" />Add</button>
</div>
<p class="mb-5 text-sm opacity-70">The services your devices live on. Settings are saved on this hub, and in settings.yaml if you prefer a file.</p>

{#if !loaded}
	<div class="flex justify-center py-20"><span class="loading loading-dots loading-lg text-primary"></span></div>
{:else}
	<div class="flex flex-col gap-3">
		{#each added as item (item.id)}
			<div id="int-{item.id}" class="card bg-base-100 border-base-content/10 border">
				<button class="flex items-center gap-3 p-4 text-left" onclick={() => (open = open === item.id ? null : item.id)} aria-expanded={open === item.id}>
					<span class="icon-bubble size-11"><Icon name={item.icon} class="size-5" /></span>
					<span class="min-w-0 grow">
						<span class="flex items-center gap-2 font-bold">{item.name}<SupportBadge support={item.support} /></span>
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
				<button class="btn btn-primary" onclick={openPicker}><Icon name="plus" class="size-5" />Add integration</button>
			</div>
		{/each}

	</div>
{/if}

{#if picker}
	<div class="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
		<button class="absolute inset-0 bg-black/50" aria-label="Close" onclick={() => (picker = false)}></button>
		<div class="bg-base-100 relative flex max-h-[85dvh] w-full max-w-xl flex-col gap-2 overflow-hidden rounded-t-2xl p-4 pb-6 sm:rounded-2xl">
			<div class="flex shrink-0 items-center">
				<h2 class="grow text-lg font-bold">Add an integration</h2>
				<button class="btn btn-ghost btn-sm btn-circle" aria-label="Close" onclick={() => (picker = false)}><Icon name="close" class="size-5" /></button>
			</div>
			<input type="search" class="input w-full shrink-0" placeholder="Search integrations" aria-label="Search integrations" bind:value={query} autocomplete="off" use:focus />
			<div class="flex min-h-0 flex-col gap-2 overflow-x-hidden overflow-y-auto">
				{#if more.length}
					<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">Add another to what you have</h3>
					{#each more as item (item.id)}
						<PickerRow {item} text={`Search for ${item.noun ?? "more"}`} action="plus" onclick={() => addMore(item)} />
					{/each}
				{/if}
				{#if matches.length}
					{#if more.length}<h3 class="mt-2 text-xs font-semibold tracking-wide uppercase opacity-60">New integrations</h3>{/if}
					{#each matches as item (item.id)}
						<PickerRow {item} text={short(item.help)} onclick={() => add(item)} />
					{/each}
				{:else if !more.length}
					<p class="py-6 text-center text-sm opacity-70">Nothing matches "{query}". Can't find yours? It may not be supported yet.</p>
				{/if}
			</div>
		</div>
	</div>
{/if}

{#if draft}
	<IntegrationDialog item={draft} isNew={draftNew} onchange={replace} ondone={finish} oncancel={cancel} />
{/if}
