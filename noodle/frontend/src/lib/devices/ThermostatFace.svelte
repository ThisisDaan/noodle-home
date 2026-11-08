<script lang="ts">
	import { command, type Device } from '../api.ts';
	import PowerButton from './PowerButton.svelte';
	import StateBar from './StateBar.svelte';

	/** A heater or thermostat on a card: one button to turn heating on or off, and the bar says what the room
	 * is now and what it is kept at. */
	let { device }: { device: Device } = $props();

	const climate = $derived(device.entities.find((e) => e.kind === 'climate'));
	const modes = $derived((climate?.attrs?.modes as string[] | undefined) ?? []);
	const mode = $derived(climate?.attrs?.mode as string | undefined);
	const on = $derived(!!mode && mode !== 'off');
	const current = $derived(climate?.attrs?.current as number | null | undefined);
	const unit = $derived(climate?.unit ?? '°C');
	const num = (v: unknown) => (typeof v === 'number' ? v.toFixed(1).replace(/\.0$/, '') : '–');
	const text = $derived(
		on
			? `${current != null ? `${num(current)} → ` : 'Keeping '}${num(climate?.state)}${unit}`
			: `Off · ${num(climate?.state)}${unit}`
	);
	let busy = $state(false);

	async function toggle() {
		if (!climate || busy) return;
		busy = true;
		try {
			await command(device, climate, { mode: on ? 'off' : (modes.find((m) => m !== 'off') ?? 'heat') });
		} finally {
			busy = false;
		}
	}
</script>

{#if climate && device.available && modes.length}
	<div class="flex h-12 items-center gap-2">
		<PowerButton {on} label={device.name} disabled={busy} onclick={toggle} />
		<StateBar {on} label={device.name} disabled={busy} onclick={toggle} {text} />
	</div>
{:else}
	<p class="flex h-12 items-center text-sm opacity-70">{climate ? `${num(climate.state)}${unit}` : ''}</p>
{/if}
