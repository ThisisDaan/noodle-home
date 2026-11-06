<script lang="ts">
	import Icon from '../Icon.svelte';
	import { live, type CardControl, type CardShow, type FlowCardSpec } from '../live.svelte';

	/** Build the flow's dashboard card without touching a file: a title, controls (switch, dial, slider, button,
	 * choice) and what to show (a reading, a status line, a graph). The ids that the flow uses are made from the
	 * labels and stay hidden. The flow editor saves the card together with the flow. */
	let { card = $bindable(), open = $bindable(false), statusNames = [] }: {
		card: FlowCardSpec | null;
		open: boolean;
		/** Variables that the flow's "Set variable" steps write: what a status line can show. */
		statusNames?: string[];
	} = $props();

	let dialog: HTMLDialogElement;
	$effect(() => {
		if (open && dialog && !dialog.open) dialog.showModal();
		if (!open && dialog?.open) dialog.close();
	});

	const TYPES: [CardControl['type'], string][] = [
		['switch', 'Switch'], ['dial', 'Dial (− and +)'], ['slider', 'Slider'], ['button', 'Button'], ['select', 'Choice']
	];
	const SHOW_TYPES: [CardShow['type'], string][] = [['value', 'A reading'], ['status', 'A status line'], ['graph', 'A graph']];

	const controls = $derived(card?.controls ?? []);
	const shows = $derived(card?.show ?? []);

	function ensure(): FlowCardSpec {
		card ??= { title: '', controls: [], show: [] };
		card.controls ??= [];
		card.show ??= [];
		return card;
	}
	const slug = (label: string) => label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').replace(/^(\d)/, 'c$1') || 'control';
	function uniqueId(label: string) {
		const base = slug(label);
		let id = base;
		for (let n = 2; ensure().controls!.some((c) => c.id === id); n++) id = `${base}_${n}`;
		return id;
	}

	function addControl(type: CardControl['type']) {
		const c = ensure();
		const label = TYPES.find(([t]) => t === type)![1].split(' ')[0];
		const defaults: Partial<CardControl> =
			type === 'dial' || type === 'slider' ? { min: 0, max: 100, step: 1, default: 50 }
			: type === 'select' ? { options: ['One', 'Two'], default: 'One' }
			: type === 'switch' ? { default: false } : {};
		c.controls!.push({ id: uniqueId(label), type, label, ...defaults });
	}
	function changeType(c: CardControl, type: CardControl['type']) {
		c.type = type;
		if (type === 'dial' || type === 'slider') Object.assign(c, { min: c.min ?? 0, max: c.max ?? 100, step: c.step ?? 1, default: Number(c.default) || c.min || 0 });
		if (type === 'select') Object.assign(c, { options: c.options?.length ? c.options : ['One', 'Two'], default: c.options?.[0] ?? 'One' });
		if (type === 'switch') c.default = false;
	}
	const remove = <T,>(list: T[], item: T) => list.splice(list.indexOf(item), 1);
	function move(list: unknown[], i: number, by: number) {
		const j = i + by;
		if (j < 0 || j >= list.length) return;
		[list[i], list[j]] = [list[j], list[i]];
	}

	function addShow(type: CardShow['type']) {
		ensure().show!.push(type === 'status' ? { type, label: 'State', variable: statusNames[0] ?? '' } : { type, label: '' });
	}
	function pickEntity(s: CardShow, value: string) {
		const [device_id, key] = value.split('|');
		s.device_id = device_id;
		s.key = key;
	}
	const entityChoices = (type: CardShow['type']) =>
		live.list
			.flatMap((d) => d.entities
				.filter((e) => (type === 'graph' ? e.kind === 'sensor' && typeof e.state === 'number' : e.kind === 'sensor' || e.kind === 'binary_sensor' || e.kind === 'climate'))
				.map((e) => ({ id: `${d.id}|${e.key}`, label: `${d.name} · ${e.name}` })))
			.sort((a, b) => a.label.localeCompare(b.label));

	function removeCard() {
		if (!confirm('Remove the dashboard card? The flow stays.')) return;
		card = null;
		open = false;
	}
	/** An empty card is no card. */
	function close() {
		if (card && !card.controls?.length && !card.show?.length) card = null;
		open = false;
	}
	const num = (v: string, fallback: number) => (v.trim() === '' || Number.isNaN(Number(v)) ? fallback : Number(v));
</script>

<dialog class="modal modal-bottom sm:modal-middle" bind:this={dialog} onclose={close}>
	<div class="modal-box flex max-h-[90vh] w-full max-w-2xl flex-col gap-4 overflow-hidden">
		<div class="flex shrink-0 items-center gap-3">
			<span class="icon-bubble"><Icon name="dial" /></span>
			<h2 class="grow text-lg font-bold">Dashboard card</h2>
			<button class="btn btn-ghost btn-sm btn-circle" aria-label="Close" onclick={close}><Icon name="close" /></button>
		</div>
		<div class="flex min-h-0 flex-col gap-5 overflow-y-auto pr-1">
			<p class="text-sm opacity-70">
				A card on the dashboard for this flow. What you put on it becomes part of the flow: use a control as a
				<b>Card control</b> step to start something, or pick it in a number (a thermostat target, a timer) to set that number from the card.
			</p>
			<label class="floating-label">
				<span>Title</span>
				<input class="input w-full" placeholder="Title of the card" value={card?.title ?? ''} oninput={(e) => (ensure().title = e.currentTarget.value)} />
			</label>

			<section class="flex flex-col gap-2">
				<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">Controls</h3>
				{#each controls as c, i (c.id)}
					<div class="bg-base-200 rounded-box flex flex-col gap-2 p-3">
						<div class="flex items-center gap-2">
							<input class="input input-sm grow" bind:value={c.label} placeholder="Name" aria-label="Control name" />
							<select class="select select-sm w-44" value={c.type} onchange={(e) => changeType(c, e.currentTarget.value as CardControl['type'])} aria-label="Control type">
								{#each TYPES as [t, name] (t)}<option value={t}>{name}</option>{/each}
							</select>
							<button class="btn btn-ghost btn-xs btn-square" aria-label="Move up" disabled={i === 0} onclick={() => move(controls, i, -1)}><Icon name="up" class="size-4" /></button>
							<button class="btn btn-ghost btn-xs btn-square" aria-label="Move down" disabled={i === controls.length - 1} onclick={() => move(controls, i, 1)}><Icon name="down" class="size-4" /></button>
							<button class="btn btn-ghost btn-xs btn-square text-error" aria-label="Remove control" onclick={() => remove(controls, c)}><Icon name="close" class="size-4" /></button>
						</div>
						{#if c.type === 'dial' || c.type === 'slider'}
							<div class="grid grid-cols-2 gap-2 sm:grid-cols-5">
								<label class="floating-label"><span>Lowest</span><input type="number" step="any" class="input input-sm w-full" value={c.min ?? 0} onchange={(e) => (c.min = num(e.currentTarget.value, 0))} /></label>
								<label class="floating-label"><span>Highest</span><input type="number" step="any" class="input input-sm w-full" value={c.max ?? 100} onchange={(e) => (c.max = num(e.currentTarget.value, 100))} /></label>
								<label class="floating-label"><span>Step</span><input type="number" step="any" min="0" class="input input-sm w-full" value={c.step ?? 1} onchange={(e) => (c.step = num(e.currentTarget.value, 1) || 1)} /></label>
								<label class="floating-label"><span>Start at</span><input type="number" step="any" class="input input-sm w-full" value={c.default ?? c.min ?? 0} onchange={(e) => (c.default = num(e.currentTarget.value, c.min ?? 0))} /></label>
								<label class="floating-label"><span>Unit</span><input class="input input-sm w-full" placeholder="°C, %, min" value={c.unit ?? ''} onchange={(e) => (c.unit = e.currentTarget.value)} /></label>
							</div>
						{:else if c.type === 'select'}
							<label class="floating-label"><span>Choices, separated by commas</span>
								<input class="input input-sm w-full" value={(c.options ?? []).join(', ')}
									onchange={(e) => { c.options = e.currentTarget.value.split(',').map((o) => o.trim()).filter(Boolean); c.default = c.options[0]; }} /></label>
						{:else if c.type === 'switch'}
							<label class="flex items-center gap-2 text-sm">
								<input type="checkbox" class="checkbox checkbox-sm" checked={c.default === true} onchange={(e) => (c.default = e.currentTarget.checked)} /> On at first
							</label>
						{/if}
					</div>
				{:else}
					<p class="text-sm opacity-60">No controls yet.</p>
				{/each}
				<div class="flex flex-wrap gap-2">
					{#each TYPES as [t, name] (t)}
						<button class="btn btn-sm btn-soft" onclick={() => addControl(t)}><Icon name="plus" class="size-4" />{name.split(' ')[0]}</button>
					{/each}
				</div>
			</section>

			<section class="flex flex-col gap-2">
				<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">Show</h3>
				{#each shows as s, i (i)}
					<div class="bg-base-200 rounded-box flex flex-wrap items-center gap-2 p-3">
						<span class="badge badge-ghost">{SHOW_TYPES.find(([t]) => t === s.type)?.[1]}</span>
						<input class="input input-sm w-32" bind:value={s.label} placeholder="Label" aria-label="Label" />
						{#if s.type === 'status'}
							<select class="select select-sm min-w-0 grow" bind:value={s.variable} aria-label="Status from">
								<option value="" disabled>Choose a status…</option>
								{#each statusNames as n (n)}<option value={n}>{n}</option>{/each}
							</select>
						{:else}
							<select class="select select-sm min-w-0 grow" value={s.device_id ? `${s.device_id}|${s.key}` : ''} onchange={(e) => pickEntity(s, e.currentTarget.value)} aria-label="Device reading">
								<option value="" disabled>Choose a reading…</option>
								{#each entityChoices(s.type) as o (o.id)}<option value={o.id}>{o.label}</option>{/each}
							</select>
						{/if}
						<button class="btn btn-ghost btn-xs btn-square" aria-label="Move up" disabled={i === 0} onclick={() => move(shows, i, -1)}><Icon name="up" class="size-4" /></button>
						<button class="btn btn-ghost btn-xs btn-square" aria-label="Move down" disabled={i === shows.length - 1} onclick={() => move(shows, i, 1)}><Icon name="down" class="size-4" /></button>
						<button class="btn btn-ghost btn-xs btn-square text-error" aria-label="Remove" onclick={() => remove(shows, s)}><Icon name="close" class="size-4" /></button>
					</div>
				{:else}
					<p class="text-sm opacity-60">Nothing to look at yet.</p>
				{/each}
				{#if shows.some((s) => s.type === 'status') && !statusNames.length}
					<p class="text-xs opacity-60">A status line shows what a <b>Set variable</b> step in this flow writes. Add one to the flow first.</p>
				{/if}
				<div class="flex flex-wrap gap-2">
					{#each SHOW_TYPES as [t, name] (t)}
						<button class="btn btn-sm btn-soft" onclick={() => addShow(t)}><Icon name="plus" class="size-4" />{name}</button>
					{/each}
				</div>
			</section>
		</div>
		<div class="flex shrink-0 gap-2">
			{#if card}<button class="btn btn-error btn-outline" onclick={removeCard}>Remove card</button>{/if}
			<button class="btn btn-primary ml-auto" onclick={close}>Done</button>
		</div>
	</div>
	<form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>
