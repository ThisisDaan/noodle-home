<script lang="ts">
	import Icon from '../Icon.svelte';
	import { api } from '../api.ts';
	import LocationMap from './LocationMap.svelte';
	import type { Integration, PanelProps } from './types.ts';

	/** Where the home is. A line says what is set; the button opens a pop-up with the map to set or change it.
	 * Picking a place sets latitude, longitude and the time zone together (sunrise and sunset, and whether a
	 * phone is home). */
	let { item, onchange }: PanelProps = $props();
	let busy = $state(false);
	let open = $state(false);
	let dialog: HTMLDialogElement;
	let message = $state<{ ok: boolean; text: string } | null>(null);

	const num = (key: string) => {
		const v = parseFloat(item.fields.find((f) => f.key === key)?.value ?? '');
		return Number.isFinite(v) ? v : null;
	};
	// Until a place is saved, the hub falls back to Amsterdam: show an empty map instead of that.
	const latitude = $derived(item.location_set ? num('latitude') : null);
	const longitude = $derived(item.location_set ? num('longitude') : null);
	const timezone = $derived(item.timezone_now ?? '');

	let unmount: ReturnType<typeof setTimeout> | undefined;
	function show() {
		message = null;
		clearTimeout(unmount);
		open = true;
		dialog.showModal();
	}
	function hide() {
		dialog.close();
	}

	async function save(place: { latitude: number; longitude: number; timezone: string }) {
		busy = true;
		message = null;
		const values: Record<string, string> = { latitude: String(place.latitude), longitude: String(place.longitude) };
		if (place.timezone) values.timezone = place.timezone;
		try {
			onchange(await api<Integration>(`/integrations/${item.id}`, { method: 'PUT', body: { values } }));
			message = { ok: true, text: place.timezone ? `Saved. Time zone: ${place.timezone}.` : 'Saved.' };
		} catch (err) {
			message = { ok: false, text: err instanceof Error ? err.message : String(err) };
		} finally {
			busy = false;
		}
	}

	function useLocation() {
		if (!navigator.geolocation) {
			message = { ok: false, text: 'This browser cannot share its location here. Pick the place on the map instead.' };
			return;
		}
		busy = true;
		message = null;
		navigator.geolocation.getCurrentPosition(
			async (pos) => {
				const { default: tzlookup } = await import('tz-lookup');
				let zone = '';
				try {
					zone = tzlookup(pos.coords.latitude, pos.coords.longitude);
				} catch {
					zone = '';
				}
				await save({ latitude: Math.round(pos.coords.latitude * 1e5) / 1e5, longitude: Math.round(pos.coords.longitude * 1e5) / 1e5, timezone: zone });
			},
			(err) => {
				busy = false;
				message = {
					ok: false,
					text: err.code === err.PERMISSION_DENIED
						? 'Location was not shared. Allow it for this site, or pick the place on the map.'
						: 'Could not find the location. Pick the place on the map instead.'
				};
			},
			{ timeout: 15000 }
		);
	}
</script>

<div class="bg-base-200 rounded-box flex flex-wrap items-center gap-3 p-3">
	<span class="icon-bubble size-10"><Icon name="home" class="size-5" /></span>
	<span class="min-w-0 grow">
		<span class="block text-sm font-medium">Home location</span>
		{#if item.location_set}
			<span class="block truncate text-xs opacity-70">{latitude?.toFixed(4)}, {longitude?.toFixed(4)} · {timezone || '–'}</span>
		{:else}
			<span class="text-warning block text-xs">Not set. Sunrise and sunset use Amsterdam until you set it.</span>
		{/if}
	</span>
	<button type="button" class="btn btn-sm {item.location_set ? '' : 'btn-primary'}" onclick={show}>{item.location_set ? 'Change' : 'Set location'}</button>
</div>

<dialog class="modal modal-bottom sm:modal-middle" bind:this={dialog} onclose={() => (unmount = setTimeout(() => (open = false), 400))}>
	<div class="modal-box flex max-w-2xl flex-col gap-3">
		<div class="flex items-center">
			<h3 class="grow text-lg font-bold">Where is your home?</h3>
			<button type="button" class="btn btn-ghost btn-sm btn-circle" aria-label="Close" onclick={hide}><Icon name="close" class="size-5" /></button>
		</div>
		<p class="text-sm opacity-70">Search for your address, click the map or drag the pin. The time zone follows from the place.</p>
		{#if open}<LocationMap {latitude} {longitude} onpick={save} />{/if}
		<div class="flex flex-wrap items-center gap-2">
			<button type="button" class="btn btn-sm" disabled={busy} onclick={useLocation}>Use this device's location</button>
			<span class="grow text-xs opacity-60">
				{#if item.location_set}{latitude?.toFixed(4)}, {longitude?.toFixed(4)} · {timezone || '–'}{/if}
			</span>
			<button type="button" class="btn btn-primary btn-sm" onclick={hide}>Done</button>
		</div>
		{#if message}<div role="alert" class="alert alert-soft text-sm {message.ok ? 'alert-success' : 'alert-error'}">{message.text}</div>{/if}
	</div>
	<form method="dialog" class="modal-backdrop"><button aria-label="Close">close</button></form>
</dialog>
