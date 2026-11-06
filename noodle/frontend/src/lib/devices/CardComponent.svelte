<script lang="ts">
	import { command, formatState, type Device } from '../api.ts';
	import SensorWidget from '../SensorWidget.svelte';
	import type { CardSlot } from './cardDesign.ts';

	/** One component of a designed card, tied to one field of the device. */
	let { device, slot }: { device: Device; slot: CardSlot } = $props();

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

	// dial and slider: a number with a range and a step (from the field, else 0..100 in steps of 1)
	const num = $derived(typeof entity?.state === 'number' ? entity.state : entity?.kind === 'light' ? (entity.brightness ?? 0) : null);
	const step = $derived(Number(entity?.attrs?.step ?? 1) || 1);
	const low = $derived(Number(entity?.attrs?.min ?? (entity?.kind === 'light' ? 1 : 0)));
	const high = $derived(Number(entity?.attrs?.max ?? 100));
	// Quick taps on + and −: count from the value we just asked for, not the one the server has confirmed so far.
	let wanted = $state<number | null>(null);
	async function nudge(direction: 1 | -1) {
		const next = Math.round(Math.min(entity?.attrs?.max ?? Infinity, Math.max(entity?.attrs?.min ?? -Infinity, (wanted ?? num ?? 0) + direction * step)) * 1000) / 1000;
		wanted = next;
		await send({ value: next });
		setTimeout(() => (wanted = null), 400);
	}
	const shown = (n: number | null) => (n === null ? '–' : String(Math.round(n * 100) / 100));
	const unit = $derived(entity?.unit ? ` ${entity.unit}` : '');
</script>

{#if !entity}
	<div class="bg-base-content/5 rounded-box flex h-full items-center justify-center px-2 text-center text-xs opacity-60" title="This field is gone from the device">–</div>
{:else if slot.component === 'switch'}
	<button type="button" class="rounded-box flex h-full w-full min-w-0 flex-col items-start justify-center px-3 text-left transition active:brightness-90 {entity.state === true ? 'bg-warning/60 text-warning-content' : 'bg-base-content/10'}"
		aria-pressed={entity.state === true} disabled={!usable} onclick={() => send({ toggle: true })}>
		<span class="w-full truncate text-xs opacity-80">{name}</span>
		<span class="font-bold">{entity.state === true ? 'On' : 'Off'}</span>
	</button>
{:else if slot.component === 'value'}
	<div class="bg-base-content/5 rounded-box flex h-full min-w-0 flex-col justify-center px-3" class:opacity-50={!device.available}>
		<span class="truncate text-xs opacity-70">{name}</span>
		<span class="truncate font-bold tabular-nums" class:text-xl={formatState(entity).length < 8} class:text-sm={formatState(entity).length >= 8}>{formatState(entity)}</span>
	</div>
{:else if slot.component === 'dial'}
	<div class="bg-base-content/5 rounded-box flex h-full min-w-0 items-center gap-1 px-1.5">
		<button type="button" class="btn btn-circle btn-sm btn-ghost" aria-label="{name}: lower" disabled={!usable} onclick={() => nudge(-1)}>−</button>
		<div class="flex min-w-0 grow flex-col items-center leading-tight">
			<span class="w-full truncate text-center text-xs opacity-70">{name}</span>
			<span class="font-bold tabular-nums">{shown(wanted ?? num)}{unit}</span>
		</div>
		<button type="button" class="btn btn-circle btn-sm btn-ghost" aria-label="{name}: raise" disabled={!usable} onclick={() => nudge(1)}>+</button>
	</div>
{:else if slot.component === 'slider'}
	<div class="bg-base-content/5 rounded-box flex h-full min-w-0 flex-col justify-center gap-0.5 px-3">
		<div class="flex items-baseline justify-between gap-2 text-xs"><span class="truncate opacity-70">{name}</span><span class="font-bold tabular-nums">{shown(num)}{unit}</span></div>
		<input type="range" class="range range-primary range-xs w-full" min={low} max={high} {step} value={num ?? low} disabled={!usable}
			aria-label={name} onchange={(e) => send(entity.kind === 'light' ? { brightness: Number(e.currentTarget.value) } : { value: Number(e.currentTarget.value) })} />
	</div>
{:else if slot.component === 'graph'}
	<div class="h-full min-h-0 overflow-hidden"><SensorWidget device_id={device.id} key={slot.key} title={slot.label} hours={6} bare /></div>
{/if}
