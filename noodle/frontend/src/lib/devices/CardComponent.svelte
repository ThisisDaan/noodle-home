<script lang="ts">
	import { api, command, formatState, isOn, type Device } from '../api.ts';
	import Icon from '../Icon.svelte';
	import HistoryGraph from './HistoryGraph.svelte';
	import InlineGraph from './InlineGraph.svelte';
	import { autoStyle, tapsOf, type CardSlot, type CardStyle } from './cardDesign.ts';
	import DialControl from './DialControl.svelte';
	import { backgroundStyle, resolve, setDevices, unitOf, valueText } from './cardText.ts';
	import { fillClassOf, fillStyle, textClass, textStyle, tintClass, tintStyle } from './colors.ts';
	import { useClock } from './clock.svelte.ts';
	import { live } from '../live.svelte';
	import { fieldsOf, isContact, isMotion, isPower } from './kinds.ts';
	import PowerButton from './PowerButton.svelte';

	/** One component of a card, tied to one field of the device (a label has none). Every card is made of these, a
	 * device's own look as much as a designed one; they are drawn like the tiles always were (a round power button,
	 * a bar that fills, a tinted status bar, a big reading). `labelled`: show the field's name (cards somebody
	 * designed; the standard looks do not need it). `preview`: in the designer, where a component a rule hides is
	 * only faded. The component's text, number format, text style and rules come from the slot (cardText.ts). */
	let { device, slot, preview = false }: { device: Device; slot: CardSlot; labelled?: boolean; preview?: boolean } = $props();
	/** a name is shown only when somebody wrote one for this component (its caption); the value is the value */
	const labelled = $derived(!!slot.label);

	const clock = useClock();
	// a template can read other devices' fields too (living_room_lamp.brightness)
	setDevices(() => Object.values(live.devices));
	// a reading can show a field of another device; everything else belongs to this one
	const src = $derived(slot.component === 'value' && slot.device && slot.device !== device.id ? live.devices[slot.device] : device);
	const entity = $derived(src ? fieldsOf(src).find((e) => e.key === slot.key) : undefined);
	const res = $derived(resolve(slot, device, clock.now, src ?? device));
	// a graph draws what its text says: {device.brightness.history.24h}; text without one falls back to the component's own field
	const graphT = $derived(res.parts?.find((p) => p.graph)?.graph);
	const gdev = $derived(graphT ? (live.devices[graphT.deviceId] ?? src ?? device) : (src ?? device));
	const gent = $derived(graphT ? (fieldsOf(gdev).find((e) => e.key === graphT.key) ?? entity) : entity);
	const name = $derived(slot.label || (graphT ? gent?.name : entity?.name) || slot.key);
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

	// a button: it presses like the real one (shows in the history, runs the automations that listen to it)
	let pressed = $state(false);
	let error = $state('');
	const mainPress = (e?: typeof entity) => e?.actions?.find((a) => /^(single|press|short_release|initial_press)$/.test(a)) ?? e?.actions?.[0] ?? 'single';
	async function pressAction(target: typeof entity, action: string) {
		if (!target) return;
		pressed = true;
		error = '';
		try {
			await api(`/devices/${encodeURIComponent(device.id)}/entities/${encodeURIComponent(target.key)}/press`, { body: { action } });
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			setTimeout(() => (pressed = false), 250);
		}
	}
	// An input that reports single / double / triple (a tap switch): tap once, twice or three times within a moment,
	// like the real one. The press is sent once the taps stop.
	const multiTap = $derived(!slot.action && !!entity && tapsOf(entity).length > 1);
	let taps = 0;
	let tapTimer: ReturnType<typeof setTimeout> | undefined;
	function press() {
		if (!entity) return;
		if (!multiTap) return void pressAction(entity, slot.action ?? mainPress(entity));
		const allowed = tapsOf(entity);
		taps = Math.min(taps + 1, allowed.length);
		clearTimeout(tapTimer);
		tapTimer = setTimeout(() => {
			const action = allowed[taps - 1];
			taps = 0;
			pressAction(entity, action);
		}, 350);
	}
	// a knob: the brighter and dimmer pair of a remote (this field is "brighter", its partner in the same group "dimmer")
	const partner = $derived(entity ? device.entities.find((e) => e.kind === 'button' && e.role === 'decrease' && (e.group ?? null) === (entity.group ?? null)) : undefined);

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
	const weight = $derived(slot.bold === false ? 'font-normal' : slot.bold ? 'font-extrabold' : 'font-bold');
	const deco = $derived(`${slot.italic ? 'italic ' : ''}${slot.underline ? 'underline' : ''}`);
	const align = $derived({ left: 'items-start text-left', center: 'items-center text-center', right: 'items-end text-right' }[slot.align ?? 'left']);
	const textColor = $derived(textClass(res.color));
	const bgCss = $derived(backgroundStyle(res.bg));
	/** a hex text colour is a style on the component (its children take it from there) */
	const inkCss = $derived(textStyle(res.color));
	// the colour of what fills or draws: {fill …}, else the text colour's tint, else the component's own
	const accent = $derived(res.fill ?? res.color);
	const tint = $derived(tintClass(accent));
	const tintCss = $derived(tintStyle(accent));
	const fillClass = $derived(fillClassOf(res.fill) || tint.split(' ')[0]);
	const fillCss = $derived(fillStyle(accent));
	const size = (long: boolean) => (style === 'text-l' ? (long ? 'text-base' : 'text-2xl') : style === 'text-m' ? 'text-lg' : 'text-sm');
</script>

{#snippet rich(fallback: string)}{#if res.parts}{#each res.parts as p, i (i)}<span style={`${p.size ? `font-size:${p.size}px;line-height:1.15;` : ''}${textStyle(p.color)}` || undefined} class="{textClass(p.color)} {p.bold ? 'font-black' : ''} {p.italic ? 'italic' : ''} {p.underline ? 'underline' : ''}">{#if p.graph}<InlineGraph graph={p.graph} />{/if}{p.text}</span>{/each}{:else}{fallback}{/if}{/snippet}

<div class="size-full {deco}" class:rounded-box={!!res.bg} class:opacity-30={res.hide} class:hidden={res.hide && !preview} style={bgCss + inkCss}>
	{#if slot.component === 'text'}
		{#if style === 'chip'}
			<div class="rounded-box flex h-full min-w-0 items-center justify-center gap-2 px-3 {tint || 'bg-base-content/5'} {textColor}" style={bgCss || tintCss}>
				{#if res.icon}<Icon name={res.icon} class="size-5 shrink-0" />{/if}
				<span class="truncate {weight}">{@render rich(text)}</span>
			</div>
		{:else}
			<div class="flex h-full min-w-0 flex-col justify-center {align} {textColor}">
				<span class="flex max-w-full items-center gap-1.5 leading-tight {weight} {size(false) === 'text-2xl' ? 'text-3xl' : size(false)}">
					{#if res.icon}<Icon name={res.icon} class="size-5 shrink-0" />{/if}<span class="truncate">{@render rich(res.text ?? slot.template ?? 'Label')}</span>
				</span>
			</div>
		{/if}
	{:else if !entity && gent && graphT}
		<!-- the graph's own field is gone from this device, but its text points at another one -->
		<HistoryGraph device={gdev} entity={gent} hours={graphT.hours} fieldKey={graphT.key} {slot} {name} {labelled} text={res.text || undefined} color={res.fill ? textClass(res.fill) : textColor} colorStyle={res.fill ? textStyle(res.fill) : inkCss} />
	{:else if !entity}
		<div class="bg-base-content/5 rounded-box grid h-full place-items-center px-2 text-center text-xs opacity-60" title="This field is gone from the device">–</div>
	{:else if slot.component === 'button'}
		<button type="button" class="btn rounded-box size-full min-h-0 px-1 text-xs capitalize active:scale-90 {pressed ? 'btn-primary' : res.bg ? 'border-0 bg-transparent shadow-none' : 'btn-soft'} {textColor}" title={name} aria-label="Press {name}" disabled={!device.available}
			onclick={press}>{@render rich(res.text ?? (slot.label || (slot.action ? slot.action.replace(/_press$/, '').replaceAll('_', ' ') : entity.name.replace(/^Button\s*/i, '') || entity.name)))}</button>
		{#if error}<p class="text-error absolute right-1 bottom-0 text-xs">{error}</p>{/if}
	{:else if slot.component === 'knob'}
		<div class="flex h-full items-center justify-center" class:opacity-50={!device.available}>
			<DialControl label={slot.label || entity.group || device.name} onstep={(d) => { const t = d > 0 ? entity : partner; pressAction(t, mainPress(t)); }} />
		</div>
	{:else if slot.component === 'switch'}
		<div class="flex h-full min-w-0 items-center gap-2">
			<PowerButton on={entity.state === true} label={name} fill={fillClassOf(res.fill)} fillCss={fillStyle(res.fill)} disabled={!usable} onclick={() => send({ toggle: true })} />
			{#if (labelled || slot.label) && slot.w >= 2}<span class="min-w-0 truncate text-sm font-medium">{name}</span>{/if}
		</div>
	{:else if slot.component === 'value'}
		{#if style === 'line' || style === 'bars' || style === 'spark'}
			<HistoryGraph device={gdev} entity={gent ?? entity} hours={graphT?.hours} fieldKey={graphT?.key} {slot} {name} {labelled} text={res.text || undefined} color={res.fill ? textClass(res.fill) : textColor} colorStyle={res.fill ? textStyle(res.fill) : inkCss} />
		{:else if style === 'chip' && look !== 'status'}
			<div class="bg-base-content/10 rounded-box relative h-full min-w-0 overflow-hidden {textColor}" class:opacity-50={!device.available} style={bgCss}>
				<span class="absolute inset-0 transition-opacity {tint || 'bg-warning/50'}" style={tintCss} class:opacity-0={!res.color && !res.fill && !isOn(device)} class:hidden={!!res.bg}></span>
				<span class="absolute inset-0 flex items-center justify-center gap-2 truncate px-2 {weight} tabular-nums">
					{#if res.icon}<Icon name={res.icon} class="size-5 shrink-0" />{/if}{labelled && res.text === undefined ? `${name} ` : ''}{@render rich(res.text ?? (typeof entity.state === 'number' ? valueText(entity, slot) : formatState(entity)))}
				</span>
			</div>
		{:else if style === 'chip' || style === 'icon'}
			<div style={bgCss || tintCss} class="rounded-box flex h-full min-w-0 items-center gap-3 px-3 transition-colors {style === 'icon' ? 'justify-center' : ''} {tint || (active ? (isMotion(entity) ? 'bg-success/20 text-success' : 'bg-warning/20 text-warning') : 'bg-base-content/5')}"
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
				{#if style === 'chip'}<span class="truncate {slot.bold === false ? 'font-normal' : slot.bold ? 'font-extrabold' : 'font-semibold'}">{labelled && res.text === undefined ? `${name}: ` : ''}{@render rich(res.text ?? (typeof entity.state === 'number' ? valueText(entity, slot) : formatState(entity)))}</span>{/if}
			</div>
		{:else if style === 'gauge'}
			<div class="relative grid h-full min-w-0 place-items-center {textColor}" class:opacity-50={!device.available}>
				<svg viewBox="0 0 36 36" class="absolute inset-0 m-auto size-full max-h-full" role="img" aria-label="{name}: {text}">
					<circle cx="18" cy="18" r="15.9" fill="none" stroke="currentColor" stroke-opacity="0.12" stroke-width="3" />
					<circle cx="18" cy="18" r="15.9" fill="none" style={textStyle(res.fill)} class={res.fill ? textClass(res.fill) : res.color ? '' : 'text-primary'} stroke="currentColor" stroke-width="3" stroke-linecap="round" pathLength="100"
						stroke-dasharray="{fill} 100" transform="rotate(-90 18 18)" />
				</svg>
				<span class="relative flex max-w-[70%] flex-col items-center leading-none">
					{#if res.text !== undefined}
						<span class="truncate text-center text-xs {weight}">{@render rich(res.text)}</span>
					{:else}
						<span class="{weight} tabular-nums">{shown(num)}<span class="text-xs font-medium opacity-60">{unitOf(entity, slot)}</span></span>
					{/if}
					{#if labelled}<span class="max-w-full truncate text-[0.65rem] opacity-60">{name}</span>{/if}
				</span>
			</div>
		{:else if style === 'bar'}
			<div class="bg-base-content/10 rounded-box relative h-full min-w-0 overflow-hidden" class:opacity-50={!device.available}>
				<div class="absolute inset-y-0 left-0 transition-[width] {fillClass || 'bg-primary/50'}" style="width: {fill}%;{fillCss}"></div>
				<span class="absolute inset-0 grid place-items-center truncate px-2 text-sm {weight} tabular-nums {textColor}">{labelled && res.text === undefined ? `${name} ` : ''}{@render rich(res.text ?? `${shown(num)}${unit}`)}</span>
			</div>
		{:else}
			<div class="flex h-full min-w-0 flex-col justify-center {align} {textColor}" class:opacity-50={!device.available || entity.state == null}>
				{#if labelled && style !== 'text-s'}<span class="max-w-full truncate text-xs opacity-70">{name}</span>{/if}
				{#if res.text === undefined && typeof entity.state === 'number'}
					<span class="max-w-full truncate leading-none tracking-tight tabular-nums {weight} {style === 'text-l' ? 'text-4xl' : style === 'text-m' ? 'text-xl' : 'text-sm'}">{labelled && style === 'text-s' ? `${name} ` : ''}{shown(entity.state)}<span class="ml-0.5 font-medium opacity-60 {style === 'text-l' ? 'text-xl' : 'text-[0.8em]'}">{unitOf(entity, slot)}</span></span>
				{:else}
					<span class="flex max-w-full items-center gap-1.5 leading-tight {weight} {size(text.length >= 10)}">
						{#if res.icon}<Icon name={res.icon} class="size-5 shrink-0" />{/if}<span class="truncate">{labelled && style === 'text-s' && res.text === undefined ? `${name}: ` : ''}{@render rich(text)}</span>
					</span>
				{/if}
			</div>
		{/if}
	{:else if slot.component === 'dial'}
		<div class="{res.bg ? '' : 'bg-base-content/10'} rounded-box flex h-full min-w-0 items-center gap-1 px-1.5">
			<button type="button" class="btn btn-circle btn-sm btn-ghost" aria-label="{name}: lower" disabled={!usable} onclick={() => nudge(-1)}>−</button>
			<div class="flex min-w-0 grow flex-col items-center leading-tight">
				{#if labelled}<span class="w-full truncate text-center text-xs opacity-70">{name}</span>{/if}
				<span class="{weight} tabular-nums {textColor}">{@render rich(res.text ?? `${shown(wanted ?? num)}${unit}`)}</span>
			</div>
			<button type="button" class="btn btn-circle btn-sm btn-ghost" aria-label="{name}: raise" disabled={!usable} onclick={() => nudge(1)}>+</button>
		</div>
	{:else if slot.component === 'slider'}
		<div class="{res.bg ? '' : 'bg-base-content/10'} rounded-box relative h-full min-w-0 overflow-hidden" class:opacity-50={!device.available}>
			<div class="{fillClass || (light ? 'bg-warning/50' : 'bg-primary/50')} absolute inset-y-0 left-0" style="width: {fill}%;{fillCss}"></div>
			<input type="range" min={low} max={high} {step} value={level} aria-label={name} disabled={!usable && !wanted}
				class="absolute inset-0 size-full cursor-pointer opacity-0"
				oninput={(e) => want(Number(e.currentTarget.value))}
				onchange={(e) => setLevel(Number(e.currentTarget.value))} />
			<span class="pointer-events-none absolute inset-0 grid place-items-center px-2 {weight} tabular-nums {textColor}">
				{#if res.text !== undefined}{@render rich(res.text)}{:else if light}{level > 0 ? `${shown(level)}%` : 'Off'}{:else}{labelled ? `${name} ` : ''}{shown(level)}{unit}{/if}
			</span>
		</div>
	{/if}
</div>
