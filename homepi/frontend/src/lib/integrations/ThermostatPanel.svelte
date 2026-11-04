<script lang="ts">
	import { api } from '../api.ts';
	import { live } from '../live.svelte.ts';
	import type { Integration, PanelProps } from './types.ts';

	let { item, onchange }: PanelProps = $props();

	const field = (key: string) => item.fields.find((f) => f.key === key)?.value ?? '';
	const pair = (device: string, key: string) => (device && key ? `${device}|${key}` : '');

	let name = $state(field('thermostat_name'));
	let sensor = $state(pair(field('thermostat_sensor_device'), field('thermostat_sensor_key')));
	let heater = $state(pair(field('thermostat_heater_device'), field('thermostat_heater_key')));
	let busy = $state(false);
	let message = $state<{ ok: boolean; text: string } | null>(null);

	// Every temperature reading and every switch, except the thermostat's own.
	const choices = (pick: (e: { kind: string; device_class: string | null }) => boolean) =>
		live.list
			.filter((d) => d.source !== 'thermostat')
			.flatMap((d) => d.entities.filter(pick).map((e) => ({ value: pair(d.id, e.key), label: `${d.name} · ${e.name}` })))
			.sort((a, b) => a.label.localeCompare(b.label));
	const sensors = $derived(choices((e) => e.kind === 'sensor' && e.device_class === 'temperature'));
	const heaters = $derived(choices((e) => e.kind === 'switch'));

	async function save() {
		const [sensorDevice, sensorKey] = sensor.split('|');
		const [heaterDevice, heaterKey] = heater.split('|');
		busy = true;
		message = null;
		try {
			onchange(
				await api<Integration>(`/integrations/${item.id}`, {
					method: 'PUT',
					body: {
						values: {
							thermostat_name: name.trim() || 'Thermostat',
							thermostat_sensor_device: sensorDevice ?? '',
							thermostat_sensor_key: sensorKey ?? '',
							thermostat_heater_device: heaterDevice ?? '',
							thermostat_heater_key: heaterKey ?? ''
						}
					}
				})
			);
			message = { ok: true, text: 'Saved. The thermostat shows up as a device in a few seconds.' };
		} catch (err) {
			message = { ok: false, text: err instanceof Error ? err.message : String(err) };
		} finally {
			busy = false;
		}
	}
</script>

<div class="flex flex-col gap-3">
	<p class="text-sm opacity-70">{item.help}</p>
	<label class="floating-label"><span>Name</span>
		<input class="input w-full" bind:value={name} placeholder="Name, e.g. Living room heating" autocomplete="off" /></label>
	<label class="floating-label"><span>Room temperature sensor</span>
		<select class="select w-full" bind:value={sensor}>
			<option value="" disabled>Pick a sensor</option>
			{#each sensors as c (c.value)}<option value={c.value}>{c.label}</option>{/each}
			{#if sensor && !sensors.some((c) => c.value === sensor)}<option value={sensor}>{sensor.replace('|', ' · ')} (not found)</option>{/if}
		</select></label>
	<label class="floating-label"><span>Heater plug</span>
		<select class="select w-full" bind:value={heater}>
			<option value="" disabled>Pick a plug or switch</option>
			{#each heaters as c (c.value)}<option value={c.value}>{c.label}</option>{/each}
			{#if heater && !heaters.some((c) => c.value === heater)}<option value={heater}>{heater.replace('|', ' · ')} (not found)</option>{/if}
		</select></label>
	{#if message}<div role="alert" class="alert alert-soft text-sm {message.ok ? 'alert-success' : 'alert-error'}">{message.text}</div>{/if}
	<div class="flex justify-end">
		<button type="button" class="btn btn-primary btn-sm" disabled={busy || !sensor || !heater} onclick={save}>
			{#if busy}<span class="loading loading-spinner loading-xs"></span>{/if}Save
		</button>
	</div>
</div>
