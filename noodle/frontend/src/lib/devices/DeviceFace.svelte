<script lang="ts">
	import type { Device } from '../api.ts';
	import ButtonFace from './ButtonFace.svelte';
	import ClimateFace from './ClimateFace.svelte';
	import LightFace from './LightFace.svelte';
	import MotionFace from './MotionFace.svelte';
	import { deviceKind } from './kinds.ts';

	/** The part of a device that matters most, chosen by what the device is. One place that decides, used by the
	 * dashboard tiles (size "tile") and the top of the device sheet (size "large"). To give a new kind of
	 * device a face: add a component here and a case in kinds.ts, and nothing else changes. */
	let { device, size = 'tile' }: { device: Device; size?: 'tile' | 'large' } = $props();
	const kind = $derived(deviceKind(device));
</script>

{#if kind === 'climate'}<ClimateFace {device} {size} />
{:else if kind === 'motion'}<MotionFace {device} {size} />
{:else if kind === 'button'}<ButtonFace {device} {size} />
{:else if kind === 'light' && size === 'tile'}<LightFace {device} />
{/if}
