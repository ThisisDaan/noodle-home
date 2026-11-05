<script lang="ts">
	import { headline, type Device } from '../api.ts';
	import ButtonFace from './ButtonFace.svelte';
	import ClimateFace from './ClimateFace.svelte';
	import ContactFace from './ContactFace.svelte';
	import LightFace from './LightFace.svelte';
	import MotionFace from './MotionFace.svelte';
	import SwitchFace from './SwitchFace.svelte';
	import { deviceKind } from './kinds.ts';

	/** The control or reading that matters most, chosen by what the device is. One place that decides. size "tile"
	 * is the bottom row of a card (always 3rem high, so cards line up); "large" is the top of the device sheet
	 * (only climate, motion and door sensors have one, see sheetFace in kinds.ts). To give a new kind of device a face: add a
	 * component here and a case in kinds.ts. */
	let { device, size = 'tile' }: { device: Device; size?: 'tile' | 'large' } = $props();
	const kind = $derived(deviceKind(device));
</script>

{#if kind === 'climate'}<ClimateFace {device} {size} />
{:else if kind === 'motion'}<MotionFace {device} {size} />
{:else if kind === 'contact'}<ContactFace {device} {size} />
{:else if size === 'tile'}
	{#if kind === 'button'}<ButtonFace {device} />
	{:else if kind === 'light'}<LightFace {device} />
	{:else if kind === 'switch'}<SwitchFace {device} />
	{:else}<p class="flex h-12 items-center text-sm opacity-70">{headline(device)}</p>
	{/if}
{/if}
