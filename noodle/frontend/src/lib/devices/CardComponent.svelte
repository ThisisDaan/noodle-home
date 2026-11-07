<script lang="ts">
	import { command, formatState, isOn, type Device } from '../api.ts';
	import Icon from '../Icon.svelte';
	import HistoryGraph from './HistoryGraph.svelte';
	import { COLORS, autoStyle, type CardSlot, type CardStyle } from './cardDesign.ts';
	import { resolve, unitOf, valueText } from './cardText.ts';
	import { useClock } from './clock.svelte.ts';
	import { isContact, isMotion, isPower } from './kinds.ts';
	import PowerButton from './PowerButton.svelte';

	/** One component of a card, tied to one field of the device (a label has none). Every card is made of these, a
	 * device's own look as much as a designed one; they are drawn like the tiles always were (a round power button,
	 * a bar that fills, a tinted status bar, a big reading). `labelled`: show the field's name (cards somebody
	 * designed; the standard looks do not need it). `preview`: in the designer, where a component a rule hides is
	 * only faded. The component's text, number format, text style and rules come from the slot (cardText.ts). */
	let { device, slot, labelled = false, preview = false }: { device: Device; slot: CardSlot; labelled?: boolean; preview?: boolean } = $props();

	const clock = useClock();
	const entity = $derived(device.entities.find((e) => e.key === slot.key));
	const name = $derived(slot.label || entity?.name || slot.key);
	const res = $derived(resolve(slot, device, clock.now));
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
	// numbers in the slot's format (decimals, thousands, unit)
	const shown = (n: number | null) => (n === null ? '–' : valueText({ ...entity!, state: n }, { ...slot, unit: '' }));
	const unit = $derived(unitOf(entity, slot) ? ` ${unitOf(entity, slot)}` : '');
	const level = $derived(wanted ?? num ?? low);
	const fill = $derived(Math.max(0, Math.min(100, ((level - low) / (high - low || 1)) * 100)));

	// what a value looks like: a status bar for motion and doors, a bar for power, a big reading for the rest
	const look = $derived(!entity ? 'reading' : isMotion(entity) || isContact(entity) ? 'status' : isPower(entity) || ['switch', 'fan', 'light'].includes(entity.kind) ? 'bar' : 'reading');
	// how a value is shown: the style chosen in the designer, else one that suits the field
	const style = $derived<CardStyle>(slot.style ?? (slot.component === 'text' ? 'text-m' : autoStyle(entity)));
	const text = $derived(res.text ?? (entity ? formatState(entity) : '–'));
	const active = $derived(entity?.state === true && device.available);

	// text style: weight, alignment and colour (a rule's colour wins)
	const weight = $derived(slot.bold ? 'font-extrabold' : 'font-bold');
	const align = $derived({ left: 'items-start text-left', center: 'items-center text-center', right: 'items-end text-right' }[slot.align ?? 'left']);
	const textColor = $derived(res.color ? COLORS[res.color].text : '');
	const tint = $derived(res.color ? COLORS[res.color].tint : '');
	const size = (long: boolean) => (style === 'text-l' ? (long ? 'text-base' : 'text-2xl') : style === 'text-m' ? 'text-lg' : 'text-sm');
</script>

<div class="size-full" class:opacity-30={res.hide} class:hidden={res.hide && !preview}>
	{#if slot.component === 'text'}
		{#if style === 'chip'}
			<div class="rounded-box flex h-full min-w-0 items-center justify-center gap-2 px-3 {tint || 'bg-base-content/5'} {textColor}">
				{#if res.icon}<Icon name={res.icon} class="size-5 shrink-0" />{/if}
				<span class="truncate {weight}">{text}</span>
			</div>
		{:else}
			<div class="flex h-full min-w-0 flex-col justify-center {align} {textColor}">
				<span class="flex max-w-full items-center gap-1.5 leading-tight {weight} {size(false) === 'text-2xl' ? 'text-3xl' : size(false)}">
					{#if res.icon}<Icon name={res.icon} class="size-5 shrink-0" />{/if}<span class="truncate">{res.text ?? slot.template ?? 'Label'}</span>
				</span>
			</div>
		{/if}
	{:else if !entity}
		<div class="bg-base-content/5 rounded-box grid h-full place-items-center px-2 text-center text-xs opacity-60" title="This field is gone from the device">–</div>
	{:else if slot.component === 'switch'}
		<div class="flex h-full min-w-0 items-center gap-2">
			<PowerButton on={entity.state === true} label={name} disabled={!usable} onclick={() => send({ toggle: true })} />
			{#if (labelled || slot.label) && slot.w >= 2}<span class="min-w-0 truncate text-sm font-medium">{name}</span>{/if}
		</div>
	{:else if slot.component === 'value'}
		{#if style === 'line' || style === 'bars' || style === 'spark'}
			<HistoryGraph {device} {entity} {slot} {name} {labelled} text={res.text} />
		{:else if style === 'chip' && look !== 'status'}
			<div class="bg-base-content/10 rounded-box relative h-full min-w-0 overflow-hidden {textColor}" class:opacity-50={!device.available}>
				<span class="absolute inset-0 transition-opacity {tint || 'bg-warning/50'}" class:opacity-0={!res.color && !isOn(device)}></span>
				<span class="absolute inset-0 flex items-center justify-center gap-2 truncate px-2 {weight} tabular-nums">
					{#if res.icon}<Icon name={res.icon} class="size-5 shrink-0" />{/if}{labelled && res.text === undefined ? `${name} ` : ''}{res.text ?? (typeof entity.state === 'number' ? valueText(entity, slot) : formatState(entity))}
				</span>
			</div>
		{:else if style === 'chip' || style === 'icon'}
			<div class="rounded-box flex h-full min-w-0 items-center gap-3 px-3 transition-colors {style === 'icon' ? 'justify-center' : ''} {tint || (active ? (isMotion(entity) ? 'bg-success/20 text-success' : 'bg-warning/20 text-warning') : 'bg-base-content/5')}"
				class:opacity-50={!device.available}>
				{#if res.icon}
					<Icon name={res.icon} class="size-5 shrink-0" />
				{:else if isMotion(entity)}
					<span class="relative grid size-3 shrink-0 place-items-center">
						{#if active}<span class="bg-success absolute inline-flex size-5 animate-ping rounded-full opacity-40"></span>{/if}
						<span class="relative size-3 rounded-full {active ? 'bg-success' : 'bg-base-content/30'}"></span>
					</span>
				{:else}
					<Icon name={isContact(entity) ? 'door' : 'bulb'} class="size-5 shrink-0 {active ? '' : 'opacity-40'}" />
				{/if}
				{#if style === 'chip'}<span class="truncate {slot.bold ? 'font-extrabold' : 'font-semibold'}">{labelled && res.text === undefined ? `${name}: ` : ''}{res.text ?? (typeof entity.state === 'number' ? valueText(entity, slot) : formatState(entity))}</span>{/if}
			</div>
		{:else if style === 'gauge'}
			<div class="relative grid h-full min-w-0 place-items-center {textColor}" class:opacity-50={!device.available}>
				<svg viewBox="0 0 36 36" class="absolute inset-0 m-auto size-full max-h-full" role="img" aria-label="{name}: {text}">
					<circle cx="18" cy="18" r="15.9" fill="none" stroke="currentColor" stroke-opacity="0.12" stroke-width="3" />
					<circle cx="18" cy="18" r="15.9" fill="none" class={res.color ? '' : 'text-primary'} stroke="currentColor" stroke-width="3" stroke-linecap="round" pathLength="100"
						stroke-dasharray="{fill} 100" transform="rotate(-90 18 18)" />
				</svg>
				<span class="relative flex max-w-[70%] flex-col items-center leading-none">
					{#if res.text !== undefined}
						<span class="truncate text-center text-xs {weight}">{res.text}</span>
					{:else}
						<span class="{weight} tabular-nums">{shown(num)}<span class="text-xs font-medium opacity-60">{unitOf(entity, slot)}</span></span>
					{/if}
					{#if labelled}<span class="max-w-full truncate text-[0.65rem] opacity-60">{name}</span>{/if}
				</span>
			</div>
		{:else if style === 'bar'}
			<div class="bg-base-content/10 rounded-box relative h-full min-w-0 overflow-hidden" class:opacity-50={!device.available}>
				<div class="absolute inset-y-0 left-0 transition-[width] {tint ? tint.split(' ')[0] : 'bg-primary/50'}" style="width: {fill}%"></div>
				<span class="absolute inset-0 grid place-items-center truncate px-2 text-sm {weight} tabular-nums {textColor}">{labelled && res.text === undefined ? `${name} ` : ''}{res.text ?? `${shown(num)}${unit}`}</span>
			</div>
		{:else}
			<div class="flex h-full min-w-0 flex-col justify-center {align} {textColor}" class:opacity-50={!device.available || entity.state == null}>
				{#if labelled && style !== 'text-s'}<span class="max-w-full truncate text-xs opacity-70">{name}</span>{/if}
				{#if res.text === undefined && typeof entity.state === 'number'}
					<span class="max-w-full truncate leading-none tracking-tight tabular-nums {weight} {style === 'text-l' ? 'text-4xl' : style === 'text-m' ? 'text-xl' : 'text-sm'}">{labelled && style === 'text-s' ? `${name} ` : ''}{shown(entity.state)}<span class="ml-0.5 font-medium opacity-60 {style === 'text-l' ? 'text-xl' : 'text-[0.8em]'}">{unitOf(entity, slot)}</span></span>
				{:else}
					<span class="flex max-w-full items-center gap-1.5 leading-tight {weight} {size(text.length >= 10)}">
						{#if res.icon}<Icon name={res.icon} class="size-5 shrink-0" />{/if}<span class="truncate">{labelled && style === 'text-s' && res.text === undefined ? `${name}: ` : ''}{text}</span>
					</span>
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
</div>
