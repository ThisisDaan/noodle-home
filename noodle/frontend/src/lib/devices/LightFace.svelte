<script lang="ts">
	import { command, type Device } from '../api.ts';
	import LevelBar from './LevelBar.svelte';
	import PowerButton from './PowerButton.svelte';
	import StateBar from './StateBar.svelte';

	/** A light on a card: a power button and one big bar to drag for the brightness. Dragging a light that is
	 * off switches it on at that level. (The sheet has the full controls, colour included.) */
	let { device }: { device: Device } = $props();

	const light = $derived(device.entities.find((e) => e.kind === 'light'));
	const dimmable = $derived(light?.brightness !== null && light?.brightness !== undefined);
	let dragging = $state<number | null>(null);
	// After a command, show what was asked until the device reports it (or 4 s pass): devices confirm late and
	// report in-between levels while they fade, which would make the bar jump back and forth.
	let wantOn = $state<boolean | null>(null);
	let wantBrightness = $state<number | null>(null);
	let settle: ReturnType<typeof setTimeout> | undefined;
	const on = $derived(wantOn ?? light?.state === true);
	const shown = $derived(dragging ?? wantBrightness ?? (on ? (light?.brightness ?? 100) : 0));
	let error = $state('');

	$effect(() => {
		if (wantOn !== null && light?.state === wantOn && wantBrightness === null) wantOn = null;
		if (wantBrightness !== null && light?.state === true && light.brightness !== null && Math.abs(light.brightness - wantBrightness) <= 2) {
			wantBrightness = null;
			wantOn = null;
		}
	});

	async function send(body: Parameters<typeof command>[2]) {
		if (!light) return;
		error = '';
		wantOn = body.brightness !== undefined ? true : (body.on ?? null);
		wantBrightness = body.brightness ?? null;
		clearTimeout(settle);
		settle = setTimeout(() => (wantOn = wantBrightness = null), 4000);
		try {
			await command(device, light, body);
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
			wantOn = wantBrightness = null;
		}
	}
</script>

{#if light && device.available}
	<div class="flex h-12 items-center gap-2">
		<PowerButton {on} label={device.name} onclick={() => send({ on: !on })} />
		{#if dimmable}
			<LevelBar value={shown} label="Brightness of {device.name}" tone="warning" bind:dragging
				oncommit={(v) => send(v > 0 ? { brightness: v } : { on: false })} />
		{:else}
			<StateBar {on} label={device.name} text={on ? 'On' : 'Off'} onclick={() => send({ on: !on })} />
		{/if}
	</div>
	{#if error}<p class="text-error absolute right-3 bottom-0.5 text-xs">{error}</p>{/if}
{/if}
