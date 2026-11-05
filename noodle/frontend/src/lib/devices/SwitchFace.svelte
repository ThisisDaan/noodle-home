<script lang="ts">
	import { command, type Device } from '../api.ts';
	import PowerButton from './PowerButton.svelte';
	import StateBar from './StateBar.svelte';
	import { isPower } from './kinds.ts';

	/** A plug or switch on a card: one big button to turn it on or off. A plug that measures power also shows
	 * what it uses right now. */
	let { device }: { device: Device } = $props();

	const sw = $derived(device.entities.find((e) => e.kind === 'switch' || e.kind === 'fan'));
	const power = $derived(device.entities.find(isPower));
	const watts = $derived(typeof power?.state === 'number' ? power.state : null);
	const on = $derived(sw?.state === true);
	let busy = $state(false);

	async function toggle() {
		if (!sw || busy) return;
		busy = true;
		try {
			await command(device, sw, { toggle: true });
		} finally {
			busy = false;
		}
	}
</script>

{#if sw && device.available}
	<div class="flex h-12 items-center gap-2">
		<PowerButton {on} label={device.name} disabled={busy} onclick={toggle} />
		<StateBar {on} label={device.name} disabled={busy} onclick={toggle}
			text={on ? (watts !== null ? `${watts < 10 ? watts.toFixed(1).replace(/\.0$/, '') : Math.round(watts)} ${power?.unit ?? 'W'}` : 'On') : 'Off'} />
	</div>
{/if}
