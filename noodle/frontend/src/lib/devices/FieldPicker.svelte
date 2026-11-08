<script lang="ts">
	import type { Device } from '../api.ts';
	import { fieldName, fieldsOf, locate, otherRef } from './cardText.ts';

	/** Pick a value by choosing the device, then the field of that device. `ref` is how a template writes it:
	 * `value` (a special), `device.brightness` (this device) or `living_room_lamp.brightness` (another). */
	let { ref, device, devices, specials = [], onpick }: {
		ref: string;
		/** the card's own device */
		device: Device;
		devices: Device[];
		/** values that belong to the component rather than a device, like `value` (this component's field) */
		specials?: { ref: string; label: string }[];
		onpick: (ref: string) => void;
	} = $props();

	const SPECIAL = '__component';
	const at = $derived(specials.some((s) => s.ref === ref) ? undefined : locate(device, ref));
	const isSpecial = $derived(specials.some((s) => s.ref === ref));
	const current = $derived(isSpecial ? SPECIAL : (at?.device.id ?? ''));
	const others = $derived(devices.filter((d) => d.id !== device.id));
	const target = $derived(current === SPECIAL || current === '' ? undefined : (current === device.id ? device : others.find((d) => d.id === current)));
	const fields = $derived(target ? fieldsOf(target) : []);
	const refOf = (d: Device, key: string) => {
		const f = fieldsOf(d).find((x) => x.key === key);
		return !f ? '' : d.id === device.id ? fieldName(device, f) : otherRef(d, f);
	};
	function pickDevice(id: string) {
		if (id === SPECIAL) return onpick(specials[0]?.ref ?? 'value');
		const d = id === device.id ? device : others.find((x) => x.id === id);
		const first = d && fieldsOf(d)[0];
		if (d && first) onpick(refOf(d, first.key));
	}
</script>

<div class="flex min-w-0 flex-wrap items-center gap-1.5">
	<select class="select select-sm w-36 min-w-0" aria-label="Device" value={current} onchange={(e) => pickDevice(e.currentTarget.value)}>
		{#if current === ''}<option value="" disabled>{ref}</option>{/if}
		{#if specials.length}<option value={SPECIAL}>This component</option>{/if}
		<option value={device.id}>{device.name} (this device)</option>
		{#each others as d (d.id)}<option value={d.id}>{d.name}</option>{/each}
	</select>
	{#if isSpecial}
		<select class="select select-sm w-40 min-w-0" aria-label="Value" value={ref} onchange={(e) => onpick(e.currentTarget.value)}>
			{#each specials as s (s.ref)}<option value={s.ref}>{s.label}</option>{/each}
		</select>
	{:else if target}
		<select class="select select-sm w-40 min-w-0" aria-label="Field" value={at?.entity.key ?? ''} onchange={(e) => onpick(refOf(target, e.currentTarget.value))}>
			{#each fields as f (f.key)}<option value={f.key}>{f.name}</option>{/each}
		</select>
	{/if}
</div>
