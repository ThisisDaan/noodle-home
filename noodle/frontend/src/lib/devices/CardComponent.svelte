<script lang="ts">
	import { command, formatState, isOn, type Device } from '../api.ts';
	import Icon from '../Icon.svelte';
	import HistoryGraph from './HistoryGraph.svelte';
	import { autoStyle, type CardSlot, type CardStyle } from './cardDesign.ts';
	import { isContact, isMotion, isPower } from './kinds.ts';
	import PowerButton from './PowerButton.svelte';

	/** One component of a card, tied to one field of the device. Every card is made of these, a device's own look
	 * as much as a designed one; they are drawn like the tiles always were (a round power button, a bar that fills,
	 * a tinted status bar, a big reading). `labelled`: show the field's name (cards somebody designed; the
	 * standard looks do not need it). */
	let { device, slot, labelled = false }: { device: Device; slot: CardSlot; labelled?: boolean } = $props();

	const entity = $derived(device.entities.find((e) => e.key === slot.key));
	const name = $derived(slot.label || entity?.name || slot.key);
	let busy = $state(false);
	const usable = $derived(device.available && !busy);

	async function send(body: Parameters<typeof command>[2]) {
		if (!entity || busy) return;
		busy = true;
		try {
			await command(device, entity, body);
		} finally {
			busy = false;
		}
	}

	// a number with a range and a step (from the field; a light's brightness is 1..100)
	const light = $derived(entity?.kind === 'light');
	const num = $derived(typeof entity?.state === 'number' ? entity.state : light ? (entity?.state === true ? (entity.brightness ?? 100) : 0) : null);
	const step = $derived(Number(entity?.attrs?.step ?? 1) || 1);
	const low = $derived(Number(entity?.attrs?.min ?? 0));
	const high = $derived(Number(entity?.attrs?.max ?? 100));
	// Quick taps and drags: show what was asked for until the server has confirmed it.
	let wanted = $state<number | null>(null);
	let settle: ReturnType<typeof setTimeout> | undefined;
	function want(value: number | null) {
		wanted = value;
		clearTimeout(settle);
		if (value !== null) settle = setTimeout(() => (wanted = null), 1500);
	}
	async function nudge(direction: 1 | -1) {
		const next = Math.round(Math.min(entity?.attrs?.max ?? Infinity, Math.max(entity?.attrs?.min ?? -Infinity, (wanted ?? num ?? 0) + direction * step)) * 1000) / 1000;
		want(next);
		await send({ value: next });
	}
	async function setLevel(value: number) {
		want(value);
		if (light) await send(value > 0 ? { brightness: value } : { on: false });
		else await send({ value });
	}
	const shown = (n: number | null) => (n === null ? '–' : String(Math.round(n * 100) / 100));
	const unit = $derived(entity?.unit ? ` ${entity.unit}` : '');
	const level = $derived(wanted ?? num ?? low);
	const fill = $derived(Math.max(0, Math.min(100, ((level - low) / (high - low || 1)) * 100)));

	// what a value looks like: a status bar for motion and doors, a bar for power, a big reading for the rest
	const look = $derived(!entity ? 'reading' : isMotion(entity) || isContact(entity) ? 'status' : isPower(entity) || ['switch', 'fan', 'light'].includes(entity.kind) ? 'bar' : 'reading');
	// how a value is shown: the style chosen in the designer, else one that suits the field
	const style = $derived<CardStyle>(slot.style ?? autoStyle(entity));
	const text = $derived(entity ? formatState(entity) : '–');
	const active = $derived(entity?.state === true && device.available);
</script>

{#if !entity}
	<div class="bg-base-content/5 rounded-box grid h-full place-items-center px-2 text-center text-xs opacity-60" title="This field is gone from the device">–</div>
{:else if slot.component === 'switch'}
	<div class="flex h-full min-w-0 items-center gap-2">
		<PowerButton on={entity.state === true} label={name} disabled={!usable} onclick={() => send({ toggle: true })} />
		{#if (labelled || slot.label) && slot.w >= 2}<span class="min-w-0 truncate text-sm font-medium">{name}</span>{/if}
	</div>
{:else if slot.component === 'value'}
	{#if style === 'line' || style === 'bars' || style === 'spark'}
		<HistoryGraph {device} {entity} {slot} {name} {labelled} />
	{:else if style === 'chip' && look !== 'status'}
		<div class="bg-base-content/10 rounded-box relative h-full min-w-0 overflow-hidden" class:opacity-50={!device.available}>
			<span class="bg-warning/50 absolute inset-0 transition-opacity" class:opacity-0={!isOn(device)}></span>
			<span class="absolute inset-0 grid place-items-center truncate px-2 font-bold tabular-nums">{labelled ? `${name} ` : ''}{text}</span>
		</div>
	{:else if style === 'chip' || style === 'icon'}
		<div class="rounded-box flex h-full min-w-0 items-center gap-3 px-3 transition-colors {style === 'icon' ? 'justify-center' : ''} {active ? (isMotion(entity) ? 'bg-success/20 text-success' : 'bg-warning/20 text-warning') : 'bg-base-content/5'}"
			class:opacity-50={!device.available}>
			{#if isMotion(entity)}
				<span class="relative grid size-3 shrink-0 place-items-center">
					{#if active}<span class="bg-success absolute inline-flex size-5 animate-ping rounded-full opacity-40"></span>{/if}
					<span class="relative size-3 rounded-full {active ? 'bg-success' : 'bg-base-content/30'}"></span>
				</span>
			{:else}
				<Icon name={isContact(entity) ? 'door' : 'bulb'} class="size-5 shrink-0 {active ? '' : 'opacity-40'}" />
			{/if}
			{#if style === 'chip'}<span class="truncate font-semibold">{labelled ? `${name}: ` : ''}{text}</span>{/if}
		</div>
	{:else if style === 'gauge'}
		<div class="relative grid h-full min-w-0 place-items-center" class:opacity-50={!device.available}>
			<svg viewBox="0 0 36 36" class="absolute inset-0 m-auto size-full max-h-full" role="img" aria-label="{name}: {text}">
				<circle cx="18" cy="18" r="15.9" fill="none" stroke="currentColor" stroke-opacity="0.12" stroke-width="3" />
				<circle cx="18" cy="18" r="15.9" fill="none" class="text-primary" stroke="currentColor" stroke-width="3" stroke-linecap="round" pathLength="100"
					stroke-dasharray="{fill} 100" transform="rotate(-90 18 18)" />
			</svg>
			<span class="relative flex flex-col items-center leading-none">
				<span class="font-bold tabular-nums">{shown(num)}<span class="text-xs font-medium opacity-60">{entity.unit ?? ''}</span></span>
				{#if labelled}<span class="max-w-full truncate text-[0.65rem] opacity-60">{name}</span>{/if}
			</span>
		</div>
	{:else if style === 'bar'}
		<div class="bg-base-content/10 rounded-box relative h-full min-w-0 overflow-hidden" class:opacity-50={!device.available}>
			<div class="bg-primary/50 absolute inset-y-0 left-0 transition-[width]" style="width: {fill}%"></div>
			<span class="absolute inset-0 grid place-items-center truncate px-2 text-sm font-bold tabular-nums">{labelled ? `${name} ` : ''}{shown(num)}{unit}</span>
		</div>
	{:else}
		<div class="flex h-full min-w-0 flex-col justify-center" class:opacity-50={!device.available || entity.state == null}>
			{#if labelled && style !== 'text-s'}<span class="truncate text-xs opacity-70">{name}</span>{/if}
			{#if typeof entity.state === 'number'}
				<span class="truncate leading-none font-bold tracking-tight tabular-nums {style === 'text-l' ? 'text-4xl' : style === 'text-m' ? 'text-xl' : 'text-sm'}">{labelled && style === 'text-s' ? `${name} ` : ''}{shown(entity.state)}<span class="ml-0.5 font-medium opacity-60 {style === 'text-l' ? 'text-xl' : 'text-[0.8em]'}">{entity.unit ?? ''}</span></span>
			{:else}
				<span class="truncate leading-tight font-bold {style === 'text-l' ? (text.length < 10 ? 'text-2xl' : 'text-base') : style === 'text-m' ? 'text-lg' : 'text-sm'}">{labelled && style === 'text-s' ? `${name}: ` : ''}{text}</span>
			{/if}
		</div>
	{/if}
{:else if slot.component === 'dial'}
	<div class="bg-base-content/10 rounded-box flex h-full min-w-0 items-center gap-1 px-1.5">
		<button type="button" class="btn btn-circle btn-sm btn-ghost" aria-label="{name}: lower" disabled={!usable} onclick={() => nudge(-1)}>−</button>
		<div class="flex min-w-0 grow flex-col items-center leading-tight">
			{#if labelled}<span class="w-full truncate text-center text-xs opacity-70">{name}</span>{/if}
			<span class="font-bold tabular-nums">{shown(wanted ?? num)}{unit}</span>
		</div>
		<button type="button" class="btn btn-circle btn-sm btn-ghost" aria-label="{name}: raise" disabled={!usable} onclick={() => nudge(1)}>+</button>
	</div>
{:else if slot.component === 'slider'}
	<div class="bg-base-content/10 rounded-box relative h-full min-w-0 overflow-hidden" class:opacity-50={!device.available}>
		<div class="{light ? 'bg-warning/50' : 'bg-primary/50'} absolute inset-y-0 left-0" style="width: {fill}%"></div>
		<input type="range" min={low} max={high} {step} value={level} aria-label={name} disabled={!usable && !wanted}
			class="absolute inset-0 size-full cursor-pointer opacity-0"
			oninput={(e) => want(Number(e.currentTarget.value))}
			onchange={(e) => setLevel(Number(e.currentTarget.value))} />
		<span class="pointer-events-none absolute inset-0 grid place-items-center px-2 font-bold tabular-nums">
			{#if light}{level > 0 ? `${shown(level)}%` : 'Off'}{:else}{labelled ? `${name} ` : ''}{shown(level)}{unit}{/if}
		</span>
	</div>
{/if}
