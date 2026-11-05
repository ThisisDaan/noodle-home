<script lang="ts">
	import type { Device } from '../api.ts';
	import { isHumidity, isTemperature } from './kinds.ts';

	/** Temperature and humidity at a glance. tile: on a card; large: the top of the device sheet. */
	let { device, size = 'tile' }: { device: Device; size?: 'tile' | 'large' } = $props();

	const temperature = $derived(device.entities.find(isTemperature));
	const humidity = $derived(device.entities.find(isHumidity));
	// Until a sensor reports again after a restart, show what it said last, dimmed.
	const value = (e?: { state: unknown; last?: unknown }) => (e?.state ?? e?.last ?? null);
	const stale = $derived(!!temperature && temperature.state == null && temperature.last != null);
	const num = (v: unknown, digits = 1) => (typeof v === 'number' ? v.toFixed(digits).replace(/\.0$/, '') : '–');
</script>

{#if size === 'large'}
	<div class="grid grid-cols-2 gap-3 text-center" class:opacity-50={!device.available || stale}>
		{#if temperature}
			<div class="bg-base-200 rounded-box p-4">
				<div class="text-4xl font-bold tabular-nums">{num(value(temperature))}<span class="text-2xl font-medium opacity-60">{temperature.unit ?? '°C'}</span></div>
				<div class="mt-1 text-sm opacity-60">Temperature</div>
			</div>
		{/if}
		{#if humidity}
			<div class="bg-base-200 rounded-box p-4">
				<div class="text-4xl font-bold tabular-nums">{num(value(humidity), 0)}<span class="text-2xl font-medium opacity-60">{humidity.unit ?? '%'}</span></div>
				<div class="mt-1 text-sm opacity-60">Humidity</div>
			</div>
		{/if}
	</div>
{:else}
	<div class="flex h-12 items-end justify-between gap-3" class:opacity-50={!device.available || stale} title={stale ? "Last known: this sensor has not reported since the hub restarted" : undefined}>
		{#if temperature}
			<span class="text-4xl leading-none font-bold tracking-tight tabular-nums">{num(value(temperature))}<span class="ml-0.5 text-xl font-medium opacity-60">{temperature.unit ?? '°C'}</span></span>
		{/if}
		{#if humidity}
			<span class="pb-0.5 text-right leading-tight">
				<span class="block text-xl font-semibold tabular-nums">{num(value(humidity), 0)}{humidity.unit ?? '%'}</span>
				<span class="block text-[11px] opacity-60">humidity</span>
			</span>
		{/if}
	</div>
{/if}
