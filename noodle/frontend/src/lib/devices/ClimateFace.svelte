<script lang="ts">
	import type { Device } from '../api.ts';
	import { isHumidity, isTemperature } from './kinds.ts';

	/** Temperature and humidity at a glance. tile: for a dashboard card; large: for the top of the device sheet. */
	let { device, size = 'tile' }: { device: Device; size?: 'tile' | 'large' } = $props();

	const temperature = $derived(device.entities.find(isTemperature));
	const humidity = $derived(device.entities.find(isHumidity));
	const num = (v: unknown, digits = 1) => (typeof v === 'number' ? v.toFixed(digits).replace(/\.0$/, '') : '–');
</script>

{#if size === 'large'}
	<div class="grid grid-cols-2 gap-3 text-center" class:opacity-50={!device.available}>
		{#if temperature}
			<div class="bg-base-200 rounded-box p-4">
				<div class="text-4xl font-bold tabular-nums">{num(temperature.state)}<span class="text-2xl font-medium opacity-60">{temperature.unit ?? '°C'}</span></div>
				<div class="mt-1 text-sm opacity-60">Temperature</div>
			</div>
		{/if}
		{#if humidity}
			<div class="bg-base-200 rounded-box p-4">
				<div class="text-4xl font-bold tabular-nums">{num(humidity.state, 0)}<span class="text-2xl font-medium opacity-60">{humidity.unit ?? '%'}</span></div>
				<div class="mt-1 text-sm opacity-60">Humidity</div>
			</div>
		{/if}
	</div>
{:else}
	<div class="flex items-baseline gap-3" class:opacity-50={!device.available}>
		{#if temperature}<span class="text-2xl font-bold tabular-nums">{num(temperature.state)}{temperature.unit ?? '°C'}</span>{/if}
		{#if humidity}<span class="text-sm tabular-nums opacity-70">{num(humidity.state, 0)}{humidity.unit ?? '%'} humidity</span>{/if}
	</div>
{/if}
