<script lang="ts">
	import DialControl from './devices/DialControl.svelte';
	import Icon from './Icon.svelte';
	import SensorWidget from './SensorWidget.svelte';
	import { api, formatState } from './api';
	import { live, type CardControl, type FlowSummary } from './live.svelte';

	/** A card a flow puts on the dashboard (its `card:` section): controls that start the flow's "Card control"
	 * triggers, and readings to look at. The values come over the websocket (live.variables, live.list), so
	 * nothing here polls. */
	let { flow }: { flow: FlowSummary } = $props();

	const card = $derived(flow.card ?? {});
	const controls = $derived(card.controls ?? []);
	const shows = $derived(card.show ?? []);
	let error = $state('');
	let busy = $state(false);

	// A dial turned quickly: remember the new value at once, so the next step starts from it and not from the
	// value the server has confirmed so far.
	let pending = $state<Record<string, number>>({});
	const raw = (c: CardControl) => live.variables?.[`${flow.id}.${c.id}`]?.value;
	function valueOf(c: CardControl): boolean | number | string {
		if (pending[c.id] !== undefined) return pending[c.id];
		const stored = raw(c);
		if (c.type === 'switch') return stored === undefined ? c.default === true : stored === 'on';
		if (c.type === 'dial' || c.type === 'slider') return stored === undefined ? Number(c.default ?? c.min ?? 0) : Number(stored);
		return stored ?? String(c.default ?? c.options?.[0] ?? '');
	}
	const label = (c: CardControl) => c.label ?? c.id;
	const unit = (c: CardControl) => (c.unit ? ` ${c.unit}` : '');
	const shown = (n: number) => String(Math.round(n * 100) / 100);

	async function send(c: CardControl, value?: boolean | number | string) {
		busy = true;
		error = '';
		try {
			await api(`/flows/${flow.id}/controls/${c.id}`, { body: value === undefined ? {} : { value } });
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			busy = false;
		}
	}
	async function step(c: CardControl, direction: 1 | -1) {
		const next = Math.min(c.max ?? Infinity, Math.max(c.min ?? -Infinity, Number(valueOf(c)) + direction * (c.step ?? 1)));
		pending[c.id] = next;
		error = '';
		try {
			await api(`/flows/${flow.id}/controls/${c.id}`, { body: { value: next } });
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			await new Promise((r) => setTimeout(r, 400)); // let the pushed value arrive before showing it again
			delete pending[c.id];
		}
	}

	function reading(s: { device_id?: string; key?: string }) {
		const device = live.list.find((d) => d.id === s.device_id);
		const entity = device?.entities.find((e) => e.key === s.key);
		return entity ? formatState(entity) : '–';
	}
</script>

<section class="bg-base-100 border-base-content/10 rounded-box mb-8 flex max-w-md flex-col gap-4 border p-4" class:opacity-60={!flow.enabled}
	aria-label={card.title ?? flow.name}>
	<div class="flex items-center gap-3">
		<span class="icon-bubble"><Icon name="dial" /></span>
		<h2 class="grow font-semibold">{card.title ?? flow.name}</h2>
		<a class="btn btn-ghost btn-xs" href="/automations/flow/{flow.id}">Open flow</a>
	</div>
	{#if !flow.enabled}
		<p class="text-xs opacity-70">This flow is switched off, so the controls do nothing. Switch it on in Automations.</p>
	{/if}

	{#each shows as s, i (i)}
		{#if s.type === 'value'}
			<div class="flex items-baseline justify-between gap-3">
				<span class="text-sm opacity-70">{s.label ?? ''}</span>
				<span class="text-3xl font-bold tabular-nums">{reading(s)}</span>
			</div>
		{:else if s.type === 'status'}
			<div class="flex items-baseline justify-between gap-3">
				<span class="text-sm opacity-70">{s.label ?? ''}</span>
				<span class="font-medium">{live.variables?.[s.variable ?? '']?.value ?? '–'}</span>
			</div>
		{:else if s.type === 'graph' && s.device_id && s.key}
			<SensorWidget device_id={s.device_id} key={s.key} title={s.label} hours={6} />
		{/if}
	{/each}

	{#each controls as c (c.id)}
		{#if c.type === 'switch'}
			<label class="flex cursor-pointer items-center justify-between gap-3">
				<span>{label(c)}</span>
				<input type="checkbox" class="toggle toggle-primary" checked={valueOf(c) === true} disabled={busy || !flow.enabled}
					onchange={(e) => send(c, e.currentTarget.checked)} />
			</label>
		{:else if c.type === 'dial'}
			<div class="flex items-center justify-between gap-3">
				<span>{label(c)}</span>
				<span class="text-2xl font-bold tabular-nums">{shown(Number(valueOf(c)))}{unit(c)}</span>
			</div>
			<div class:pointer-events-none={!flow.enabled}>
				<DialControl label={label(c)} onstep={(d) => step(c, d)} />
			</div>
		{:else if c.type === 'slider'}
			<label class="flex flex-col gap-1">
				<span class="flex justify-between"><span>{label(c)}</span><span class="tabular-nums">{shown(Number(valueOf(c)))}{unit(c)}</span></span>
				<input type="range" class="range range-primary range-sm" min={c.min ?? 0} max={c.max ?? 100} step={c.step ?? 1}
					value={Number(valueOf(c))} disabled={busy || !flow.enabled} onchange={(e) => send(c, Number(e.currentTarget.value))} />
			</label>
		{:else if c.type === 'button'}
			<button class="btn btn-soft" disabled={busy || !flow.enabled} onclick={() => send(c)}>{label(c)}</button>
		{:else if c.type === 'select'}
			<label class="floating-label">
				<span>{label(c)}</span>
				<select class="select w-full" value={String(valueOf(c))} disabled={busy || !flow.enabled} onchange={(e) => send(c, e.currentTarget.value)}>
					{#each c.options ?? [] as o (o)}<option value={o}>{o}</option>{/each}
				</select>
			</label>
		{/if}
	{/each}
	{#if error}<p class="text-error text-xs">{error}</p>{/if}
</section>
