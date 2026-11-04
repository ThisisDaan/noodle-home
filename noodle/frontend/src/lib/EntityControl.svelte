<script lang="ts">
	import { command, type CommandBody, formatState, type Device, type Entity } from './api';

	let { device, entity }: { device: Device; entity: Entity } = $props();

	let busy = $state(false);
	let error = $state('');
	// While dragging the slider, show the local value instead of the device's.
	let dragging = $state<number | null>(null);
	// After a command, show what was asked until the device reports it (or 4 s pass):
	// devices confirm late and report in-between levels while they fade.
	let wantOn = $state<boolean | null>(null);
	let wantBrightness = $state<number | null>(null);
	let settle: ReturnType<typeof setTimeout> | undefined;

	const on = $derived(wantOn ?? entity.state === true);
	const shown = $derived(dragging ?? wantBrightness ?? entity.brightness ?? 0);

	$effect(() => {
		if (wantOn !== null && entity.state === wantOn) wantOn = null;
		if (wantBrightness !== null && entity.state === true && entity.brightness !== null &&
			Math.abs(entity.brightness - wantBrightness) <= 2) wantBrightness = null;
	});

	async function send(body: CommandBody) {
		busy = true;
		error = '';
		wantOn = body.brightness !== undefined ? true : (body.on ?? null);
		wantBrightness = body.brightness ?? null;
		clearTimeout(settle);
		settle = setTimeout(() => (wantOn = wantBrightness = null), 4000);
		try {
			await command(device, entity, body);
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
			wantOn = wantBrightness = null;
		} finally {
			busy = false;
		}
	}
</script>

{#if entity.kind === 'number'}
	<div class="flex items-center justify-between gap-3">
		<span class="text-sm">{entity.name}</span>
		<div class="join">
			<button class="btn btn-sm join-item" disabled={busy} aria-label="Lower"
				onclick={() => send({ value: Number(entity.state) - 0.5 })}>−</button>
			<span class="btn btn-sm join-item pointer-events-none tabular-nums">{Number(entity.state).toFixed(1)}{entity.unit ?? ''}</span>
			<button class="btn btn-sm join-item" disabled={busy} aria-label="Raise"
				onclick={() => send({ value: Number(entity.state) + 0.5 })}>+</button>
		</div>
	</div>
	{#if error}<p class="text-error text-xs">{error}</p>{/if}
{:else if entity.kind === 'cover'}
	<div class="flex flex-col gap-2">
		<div class="flex items-center justify-between gap-3">
			<span class="text-sm">{entity.name} <span class="opacity-60">{formatState(entity)}</span></span>
			<div class="join">
				<button class="btn btn-sm join-item" disabled={busy || !device.available} onclick={() => send({ action: 'open' })}>Open</button>
				<button class="btn btn-sm join-item" disabled={busy || !device.available} onclick={() => send({ action: 'stop' })}>Stop</button>
				<button class="btn btn-sm join-item" disabled={busy || !device.available} onclick={() => send({ action: 'close' })}>Close</button>
			</div>
		</div>
		{#if entity.attrs?.position != null}
			<input type="range" min="0" max="100" class="range range-primary range-xs" value={entity.attrs.position}
				disabled={!device.available} aria-label="Position" onchange={(e) => send({ position: Number(e.currentTarget.value) })} />
		{/if}
		{#if error}<p class="text-error text-xs">{error}</p>{/if}
	</div>
{:else if entity.kind === 'lock'}
	<div class="flex items-center justify-between gap-3">
		<span class="text-sm">{entity.name} <span class="opacity-60">{formatState(entity)}</span></span>
		<button class="btn btn-sm" disabled={busy || !device.available}
			onclick={() => send({ action: entity.state === 'locked' ? 'unlock' : 'lock' })}>{entity.state === 'locked' ? 'Unlock' : 'Lock'}</button>
	</div>
	{#if error}<p class="text-error text-xs">{error}</p>{/if}
{:else if entity.kind === 'climate'}
	<div class="flex flex-col gap-2">
		<div class="flex items-center justify-between gap-3">
			<span class="text-sm">{entity.name}{entity.attrs?.current != null ? ' · now ' + entity.attrs.current + (entity.unit ?? '') : ''}</span>
			<div class="join">
				<button class="btn btn-sm join-item" disabled={busy} aria-label="Lower"
					onclick={() => send({ value: Number(entity.state) - (entity.attrs?.step ?? 0.5) })}>−</button>
				<span class="btn btn-sm join-item pointer-events-none tabular-nums">{entity.state ?? '–'}{entity.unit ?? ''}</span>
				<button class="btn btn-sm join-item" disabled={busy} aria-label="Raise"
					onclick={() => send({ value: Number(entity.state) + (entity.attrs?.step ?? 0.5) })}>+</button>
			</div>
		</div>
		{#if entity.attrs?.modes?.length}
			<select class="select select-sm" value={entity.attrs.mode} disabled={busy} aria-label="Mode"
				onchange={(e) => send({ mode: e.currentTarget.value })}>
				{#each entity.attrs.modes as mode (mode)}<option value={mode}>{mode}</option>{/each}
			</select>
		{/if}
		{#if error}<p class="text-error text-xs">{error}</p>{/if}
	</div>
{:else if entity.kind === 'light' || entity.kind === 'switch' || entity.kind === 'fan'}
	<div class="flex flex-col gap-2">
		<label class="flex items-center justify-between gap-3">
			<span class="text-sm">{entity.kind === 'light' ? 'Light' : entity.kind === 'fan' ? 'Fan' : entity.key === 'heat' ? 'Thermostat' : 'Power'}</span>
			<input type="checkbox" class="toggle toggle-primary" checked={on} disabled={busy || !device.available}
				onchange={(e) => send({ on: e.currentTarget.checked })} />
		</label>
		{#if entity.kind === 'light' && entity.brightness !== null}
			<div class="flex items-center gap-3">
				<input type="range" min="1" max="100" class="range range-primary range-xs grow" value={shown}
					disabled={!device.available} aria-label="Brightness"
					oninput={(e) => (dragging = Number(e.currentTarget.value))}
					onchange={(e) => {
						const value = Number(e.currentTarget.value);
						dragging = null;
						send({ brightness: value });
					}} />
				<span class="w-10 text-right text-xs tabular-nums opacity-70">{on ? `${shown}%` : 'off'}</span>
			</div>
		{/if}
		{#if entity.kind === 'light' && entity.attrs?.color_temp_range && entity.attrs.can?.includes('color_temp')}
			<div class="flex items-center gap-3">
				<span class="w-10 text-xs opacity-70">Warm</span>
				<input type="range" min={entity.attrs.color_temp_range[0]} max={entity.attrs.color_temp_range[1]} step="50"
					class="range range-xs grow" value={entity.attrs.color_temp ?? entity.attrs.color_temp_range[0]}
					disabled={!device.available} aria-label="Colour temperature"
					onchange={(e) => send({ color_temp: Number(e.currentTarget.value) })} />
				<span class="w-10 text-right text-xs opacity-70">Cool</span>
			</div>
		{/if}
		{#if entity.kind === 'light' && entity.attrs?.can?.includes('color')}
			<div class="flex items-center gap-3">
				<span class="w-10 text-xs opacity-70">Colour</span>
				<input type="range" min="0" max="360" class="range range-xs grow" value={entity.attrs.color?.h ?? 0}
					disabled={!device.available} aria-label="Colour"
					onchange={(e) => send({ color: { h: Number(e.currentTarget.value), s: Math.max(entity.attrs?.color?.s ?? 0, 70) } })} />
			</div>
		{/if}
		{#if entity.kind === 'fan' && entity.attrs?.modes?.length}
			<select class="select select-sm" value={entity.attrs.mode} disabled={busy} aria-label="Fan mode"
				onchange={(e) => send({ mode: e.currentTarget.value })}>
				{#each entity.attrs.modes as mode (mode)}<option value={mode}>{mode}</option>{/each}
			</select>
		{/if}
		{#if error}<p class="text-error text-xs">{error}</p>{/if}
	</div>
{:else}
	<div class="flex items-center justify-between gap-3 text-sm">
		<span class="opacity-70">{entity.name}</span>
		<span class:badge-success={entity.kind === 'binary_sensor' && entity.state === true}
			class="badge badge-soft badge-sm tabular-nums">{formatState(entity)}</span>
	</div>
{/if}
