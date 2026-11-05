<script lang="ts">
	import { command, type Device } from '../api.ts';

	/** A light on a dashboard tile: brightness in one drag. Dragging a light that is off switches it on at that
	 * level. (The sheet has the full controls, colour included: EntityControl.) */
	let { device }: { device: Device } = $props();

	const light = $derived(device.entities.find((e) => e.kind === 'light'));
	const dimmable = $derived(light?.brightness !== null && light?.brightness !== undefined);
	let dragging = $state<number | null>(null);
	const shown = $derived(dragging ?? (light?.state ? (light.brightness ?? 0) : 0));
	let error = $state('');

	async function set(value: number) {
		dragging = null;
		if (!light) return;
		error = '';
		try {
			await command(device, light, value > 0 ? { brightness: value } : { on: false });
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}
</script>

{#if light && dimmable && device.available}
	<div class="relative z-10 flex items-center gap-2">
		<input type="range" min="0" max="100" class="range range-primary range-xs grow" value={shown} aria-label="Brightness of {device.name}"
			oninput={(e) => (dragging = Number(e.currentTarget.value))}
			onchange={(e) => set(Number(e.currentTarget.value))} />
		<span class="w-9 text-right text-xs tabular-nums opacity-70">{shown}%</span>
	</div>
	{#if error}<p class="text-error text-xs">{error}</p>{/if}
{/if}
