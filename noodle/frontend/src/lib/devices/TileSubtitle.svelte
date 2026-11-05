<script lang="ts">
	import { ago, formatState, type Device } from '../api.ts';
	import { agoText, useClock } from './clock.svelte.ts';
	import { contactEntity, deviceKind, presenceEntity } from './kinds.ts';

	/** The line under a card's name: when a button was last used or motion was last seen, else the integration and
	 * when the device last reported. All of it comes with the device (pushed over the websocket). */
	let { device }: { device: Device } = $props();

	const clock = useClock();
	const kind = $derived(deviceKind(device));
	const text = $derived.by(() => {
		if (!device.available) return 'Offline';
		if (kind === 'button') {
			const all = device.entities.filter((e) => e.kind === 'button');
			const newest = all.filter((e) => e.changed).sort((a, b) => b.changed! - a.changed!)[0];
			return newest
				? `Last: ${newest.name}${all.length > 1 && newest.group ? ` (${newest.group})` : ''} · ${agoText(newest.changed, clock.now)}`
				: 'Not used yet';
		}
		if (kind === 'motion') {
			const e = presenceEntity(device);
			if (!e?.changed) return 'No activity yet';
			// After a restart the sensor stays quiet until something moves: say when it last did.
			return e.state === null ? `Last activity ${agoText(e.changed, clock.now)}` : `${formatState(e)} since ${agoText(e.changed, clock.now).replace(' ago', '')}`;
		}
		if (kind === 'contact') {
			const e = contactEntity(device);
			if (!e?.changed) return 'No change yet';
			return `${e.state ? 'Open' : 'Closed'} since ${agoText(e.changed, clock.now).replace(' ago', '')}`;
		}
		return `${device.source[0].toUpperCase()}${device.source.slice(1)} · ${ago(device.last_seen)}`;
	});
</script>

{text}
