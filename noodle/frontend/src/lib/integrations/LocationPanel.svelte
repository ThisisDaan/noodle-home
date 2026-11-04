<script lang="ts">
	import { api } from '../api.ts';
	import type { Integration, PanelProps } from './types.ts';

	let { item, onchange }: PanelProps = $props();
	let busy = $state(false);
	let message = $state<{ ok: boolean; text: string } | null>(null);

	const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
	const hubZone = $derived(item.timezone_now ?? '');
	const differs = $derived(!!browserZone && !!hubZone && browserZone !== hubZone && !hubZone.match(/^[A-Z]{2,5}$/));

	async function put(values: Record<string, string>, done: string) {
		busy = true;
		message = null;
		try {
			onchange(await api<Integration>(`/integrations/${item.id}`, { method: 'PUT', body: { values } }));
			message = { ok: true, text: done };
		} catch (err) {
			message = { ok: false, text: err instanceof Error ? err.message : String(err) };
		} finally {
			busy = false;
		}
	}

	const useZone = () => put({ timezone: browserZone }, `Time zone set to ${browserZone}.`);

	function useLocation() {
		if (!navigator.geolocation) {
			message = { ok: false, text: 'This browser cannot share its location here. Type the numbers in instead.' };
			return;
		}
		busy = true;
		message = null;
		navigator.geolocation.getCurrentPosition(
			(pos) => {
				busy = false;
				put(
					{ latitude: pos.coords.latitude.toFixed(4), longitude: pos.coords.longitude.toFixed(4) },
					'Location set to where this device is now.'
				);
			},
			(err) => {
				busy = false;
				message = {
					ok: false,
					text:
						err.code === err.PERMISSION_DENIED
							? 'Location was not shared. Allow it for this site, or type the numbers in instead.'
							: 'Could not find the location. Type the numbers in instead (a maps app shows them when you hold on your home).'
				};
			},
			{ timeout: 15000 }
		);
	}
</script>

{#if item.location_set === false}
	<div role="alert" class="alert alert-warning alert-soft text-sm">
		Your home's location is not set, so sunrise and sunset use Amsterdam. Set it for correct "at sunset" flows and for knowing when a phone is home.
	</div>
{/if}

<div class="flex flex-wrap items-center gap-2">
	<button type="button" class="btn btn-sm" disabled={busy} onclick={useLocation}>Use this device's location</button>
	{#if browserZone}
		<button type="button" class="btn btn-sm" disabled={busy || browserZone === hubZone} onclick={useZone}>Use this browser's time zone ({browserZone})</button>
	{/if}
</div>
<p class="text-xs opacity-60">
	The hub's clock: {item.time_now} ({hubZone}).{differs ? ` This browser is in ${browserZone}.` : ''}
	Browsers only share their location over https or on the machine itself; otherwise type it in.
</p>
{#if message}<div role="alert" class="alert alert-soft text-sm {message.ok ? 'alert-success' : 'alert-error'}">{message.text}</div>{/if}
