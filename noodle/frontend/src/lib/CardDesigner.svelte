<script lang="ts">
	import Icon from './Icon.svelte';
	import { cardDesigner } from './designer.svelte';
	import { COMPONENTS, SIZES, cells, compatible, fits, slotCount, type CardComponentType, type CardDesign, type CardSize } from './devices/cardDesign.ts';
	import { layout } from './layout.svelte';
	import { live } from './live.svelte';

	let dialog: HTMLDialogElement;

	const device = $derived(cardDesigner.deviceId ? live.devices[cardDesigner.deviceId] : undefined);
	let draft = $state<CardDesign>({ size: 'small', slots: [] });
	/** The slot being worked on: an empty one to fill (add) or a slot of the card (edit). */
	let pick = $state<{ at: number; index: number } | null>(null);
	let component = $state<CardComponentType | ''>('');
	let key = $state('');
	let label = $state('');
	let note = $state('');

	$effect(() => {
		if (device && !dialog.open) {
			const saved = layout.cards[device.id];
			draft = saved ? { size: saved.size, slots: saved.slots.map((s) => ({ ...s })) } : { size: 'small', slots: [] };
			pick = null;
			note = '';
			dialog.showModal();
		}
		if (!device && dialog?.open) dialog.close();
	});

	const size = $derived(SIZES[draft.size]);
	const slotAt = (at: number) => draft.slots.findIndex((s) => cells(draft.size, s.at, s.component)?.includes(at));
	const choices = $derived(
		pick && pick.index < 0
			? (Object.keys(COMPONENTS) as CardComponentType[]).filter((c) => fits(draft, pick!.at, c) && device?.entities.some((e) => compatible(c, e)))
			: []
	);
	const fields = $derived(component && device ? device.entities.filter((e) => compatible(component as CardComponentType, e)) : []);

	function choose(at: number) {
		note = '';
		const index = slotAt(at);
		pick = { at: index >= 0 ? draft.slots[index].at : at, index };
		if (index >= 0) {
			const s = draft.slots[index];
			component = s.component;
			key = s.key;
			label = s.label ?? '';
		} else {
			component = '';
			key = '';
			label = '';
		}
	}
	function pickComponent(c: CardComponentType) {
		component = c;
		key = device?.entities.find((e) => compatible(c, e))?.key ?? '';
		label = '';
	}
	function apply() {
		if (!pick || !component || !key) return;
		const slot = { at: pick.at, component, key, ...(label.trim() ? { label: label.trim() } : {}) };
		if (pick.index >= 0) draft.slots[pick.index] = slot;
		else draft.slots.push(slot);
		pick = null;
	}
	function removeSlot() {
		if (pick && pick.index >= 0) draft.slots.splice(pick.index, 1);
		pick = null;
	}
	function resize(next: CardSize) {
		const kept: CardDesign = { size: next, slots: [] };
		for (const s of draft.slots) if (fits(kept, s.at, s.component)) kept.slots.push(s);
		const dropped = draft.slots.length - kept.slots.length;
		draft = kept;
		pick = null;
		note = dropped ? `${dropped} component${dropped > 1 ? 's' : ''} did not fit the ${SIZES[next].label.toLowerCase()} size and ${dropped > 1 ? 'were' : 'was'} removed.` : '';
	}

	function save() {
		if (!device) return;
		layout.setCard(device.id, draft.slots.length ? $state.snapshot(draft) : null);
		cardDesigner.close();
	}
	function reset() {
		if (!device) return;
		layout.setCard(device.id, null);
		cardDesigner.close();
	}
	const fieldName = (k: string) => device?.entities.find((e) => e.key === k)?.name ?? k;
</script>

<dialog class="modal modal-bottom sm:modal-middle" bind:this={dialog} onclose={() => cardDesigner.close()}>
	<div class="modal-box flex max-h-[92vh] w-full max-w-xl flex-col gap-4 overflow-hidden">
		{#if device}
			<div class="flex shrink-0 items-center gap-3">
				<span class="icon-bubble"><Icon name="edit" /></span>
				<h2 class="grow text-lg font-bold">Design the card of {device.name}</h2>
				<button class="btn btn-ghost btn-sm btn-circle" aria-label="Close" onclick={() => cardDesigner.close()}><Icon name="close" /></button>
			</div>
			<div class="flex min-h-0 flex-col gap-4 overflow-y-auto pr-1">
				<div class="flex flex-wrap items-center gap-2">
					<span class="text-sm opacity-70">Size</span>
					<div class="join">
						{#each Object.entries(SIZES) as [id, s] (id)}
							<button class="btn btn-sm join-item" class:btn-primary={draft.size === id} onclick={() => resize(id as CardSize)}>{s.label} <span class="text-xs opacity-60">{s.hint}</span></button>
						{/each}
					</div>
				</div>
				{#if note}<p class="text-xs opacity-70" role="status">{note}</p>{/if}

				<div class="bg-base-200 rounded-box p-3">
					<div class="mx-auto grid max-w-md gap-2" style="grid-template-columns: repeat({size.cols}, minmax(0, 1fr)); grid-auto-rows: 3.25rem;" aria-label="Card slots">
						{#each Array.from({ length: slotCount(draft.size) }, (_, i) => i) as at (at)}
							{@const index = slotAt(at)}
							{#if index < 0}
								<button type="button" class="border-base-content/20 hover:bg-base-300 rounded-box border border-dashed text-lg opacity-70" class:ring-2={pick?.at === at && pick.index < 0}
									style="grid-column: {(at % size.cols) + 1}; grid-row: {Math.floor(at / size.cols) + 1};" aria-label="Add a component to slot {at + 1}" onclick={() => choose(at)}>+</button>
							{:else if draft.slots[index].at === at}
								{@const s = draft.slots[index]}
								{@const c = COMPONENTS[s.component]}
								<button type="button" class="bg-primary/20 hover:bg-primary/30 rounded-box flex min-w-0 flex-col items-start justify-center px-3 text-left text-sm" class:ring-2={pick?.index === index}
									style="grid-column: {(at % size.cols) + 1} / span {c.w}; grid-row: {Math.floor(at / size.cols) + 1} / span {c.h};" onclick={() => choose(at)}>
									<span class="w-full truncate font-semibold">{s.label || fieldName(s.key)}</span>
									<span class="text-xs opacity-70">{c.label}</span>
								</button>
							{/if}
						{/each}
					</div>
				</div>

				{#if pick}
					<div class="bg-base-200 rounded-box flex flex-col gap-3 p-3">
						{#if pick.index < 0 && !component}
							<span class="text-sm font-semibold">What goes in this slot?</span>
							<div class="flex flex-wrap gap-2">
								{#each choices as c (c)}
									<button class="btn btn-sm btn-soft" title={COMPONENTS[c].hint} onclick={() => pickComponent(c)}>{COMPONENTS[c].label}</button>
								{:else}
									<span class="text-sm opacity-60">Nothing fits here. Try another slot or a bigger size.</span>
								{/each}
							</div>
						{:else}
							<div class="flex flex-wrap items-center gap-2">
								<span class="badge badge-primary">{component && COMPONENTS[component].label}</span>
								<select class="select select-sm min-w-0 grow" bind:value={key} aria-label="Field">
									{#each fields as e (e.key)}<option value={e.key}>{e.name}</option>{/each}
								</select>
							</div>
							<label class="floating-label"><span>Label (optional)</span>
								<input class="input input-sm w-full" bind:value={label} placeholder={fieldName(key)} maxlength="40" /></label>
							<div class="flex gap-2">
								{#if pick.index >= 0}<button class="btn btn-sm btn-error btn-outline" onclick={removeSlot}>Remove</button>{/if}
								<button class="btn btn-sm" onclick={() => (pick = null)}>Cancel</button>
								<button class="btn btn-sm btn-primary ml-auto" disabled={!key} onclick={apply}>{pick.index >= 0 ? 'Update' : 'Add'}</button>
							</div>
						{/if}
					</div>
				{:else}
					<p class="text-sm opacity-60">Tap a slot to add something to the card, or a component to change it. A device without a design keeps its own look.</p>
				{/if}
			</div>
			<div class="flex shrink-0 gap-2">
				{#if layout.cards[device.id]}<button class="btn btn-outline" onclick={reset}>Back to the default look</button>{/if}
				<button class="btn btn-primary ml-auto" onclick={save}>Save</button>
			</div>
		{/if}
	</div>
	<form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>
