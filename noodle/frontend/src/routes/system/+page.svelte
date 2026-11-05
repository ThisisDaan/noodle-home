<script lang="ts">
	import { api } from '#lib/api.ts';
	import IntegrationForm from '#lib/integrations/IntegrationForm.svelte';
	import type { Integration } from '#lib/integrations/types.ts';
	import { live } from '#lib/live.svelte.ts';

	// Noodle's own settings only. Everything that belongs to a service (Zigbee2MQTT, Matter, Ntfy, ...) is on its
	// integration under Integrations.

	// Set by the Noodle Android app's WebView, so its settings are reachable from the same interface.
	const phoneApp = typeof window !== 'undefined' ? (window as any).NoodleApp : undefined;
	let error = $state('');

	// The hub's own settings: home name, location, time zone, addresses.
	let hubItem = $state<Integration | undefined>();
	$effect(() => {
		api<Integration[]>('/integrations').then((list) => (hubItem = list.find((i) => i.always))).catch(() => {});
	});

	// Updates
	type UpdateInfo = { current: string; latest: string | null; available: boolean; url: string | null; notes: string; error: string | null; can_install: boolean };
	let update = $state<UpdateInfo | null>(null);
	let updateBusy = $state('');
	let restarting = $state(false);

	async function checkUpdate() {
		updateBusy = 'Checking…';
		try {
			update = await api<UpdateInfo>('/update/check', { body: {} });
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			updateBusy = '';
		}
	}

	async function installUpdate() {
		if (!confirm(`Update Noodle to ${update?.latest}? It restarts for a few seconds.`)) return;
		updateBusy = 'Downloading…';
		try {
			await api('/update/install', { body: {} });
			restarting = true;
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			updateBusy = '';
		}
	}

	// The hub restarts into the new version; when the live connection comes back, load the new interface.
	let wasDown = false;
	$effect(() => {
		if (!restarting) return;
		if (!live.connected) wasDown = true;
		else if (wasDown) location.reload();
	});

	// Phone notifications through the Noodle app (Ntfy has its own settings under Integrations).
	let phones = $state<number | null>(null);
	let notifyResult = $state('');
	$effect(() => {
		api<{ app_connections: number }>('/notify').then((n) => (phones = n.app_connections)).catch(() => {});
	});

	async function testNotify() {
		try {
			const res = await api<{ local: number; ntfy: boolean }>('/notify/test', { body: {} });
			const via = [res.local ? `the Noodle app (${res.local} connected)` : '', res.ntfy ? 'ntfy' : ''].filter(Boolean).join(' and ');
			notifyResult = `Sent through ${via}. It should show up on your phone within a few seconds.`;
		} catch (err) {
			notifyResult = err instanceof Error ? err.message : String(err);
		}
	}

	// History
	let historyDays = $state<number | null>(null);
	$effect(() => {
		api<{ days: number }>('/settings/history').then((s) => (historyDays = s.days));
	});

	async function setHistory(days: number) {
		historyDays = (await api<{ days: number }>('/settings/history', { method: 'PUT', body: { days } })).days;
	}
</script>

<div class="mb-4">
	<h1 class="text-2xl font-bold">System</h1>
	<p class="text-sm opacity-70">Settings of Noodle itself. Services like Zigbee2MQTT, Matter and Ntfy are under Integrations.</p>
</div>
{#if error}<div role="alert" class="alert alert-error alert-soft mb-4">{error}</div>{/if}

<div class="card bg-base-100 mb-4 shadow-sm">
	<div class="card-body gap-2 p-4">
		<h2 class="card-title text-base">Noodle {update?.current ?? ''}</h2>
		{#if restarting}
			<p class="text-sm"><span class="loading loading-dots loading-sm"></span> Updating… this page reloads when Noodle is back.</p>
		{:else}
			{#if update?.error}
				<p class="text-sm opacity-70">{update.error}</p>
			{:else if update && !update.available}
				<p class="text-sm opacity-70">You are up to date.</p>
			{:else if update?.available}
				<p class="text-sm">Version {update.latest} is available.
					{#if update.url}<a class="link" href={update.url} target="_blank" rel="noopener">What changed</a>{/if}</p>
			{/if}
			<div class="flex flex-wrap gap-2">
				<button class="btn btn-sm" onclick={checkUpdate} disabled={!!updateBusy}>{updateBusy || 'Check for updates'}</button>
				{#if update?.available}
					{#if update.can_install}
						<button class="btn btn-primary btn-sm" onclick={installUpdate} disabled={!!updateBusy}>Update to {update.latest}</button>
					{:else}
						<span class="text-sm opacity-70">Update by hand: <code>docker compose pull && docker compose up -d</code></span>
					{/if}
				{/if}
			</div>
		{/if}
	</div>
</div>

{#if hubItem}
	<div class="card bg-base-100 mb-4 shadow-sm">
		<div class="card-body gap-2 p-4">
			<h2 class="card-title text-base">Home</h2>
			<IntegrationForm item={hubItem} onchange={(updated) => (hubItem = updated)} removable={false} />
		</div>
	</div>
{/if}

<div class="card bg-base-100 mb-4 shadow-sm">
	<div class="card-body gap-2 p-4">
		<h2 class="card-title text-base">
			<span class="status" class:status-success={!!phones} class:status-neutral={!phones}></span>
			Phone notifications
		</h2>
		<p class="text-sm opacity-70">
			{#if phones}{phones} phone{phones > 1 ? 's' : ''} connected through the Noodle app. Works on the home network without internet.
			{:else}No phone is connected. Open the Noodle app and turn on Settings › Notifications on this network.{/if}
		</p>
		<button class="btn btn-sm w-fit" onclick={testNotify}>Send test</button>
		{#if notifyResult}<p class="text-xs">{notifyResult}</p>{/if}
	</div>
</div>

{#if phoneApp}
	<div class="card bg-base-100 mb-4 shadow-sm">
		<div class="card-body gap-2 p-4">
			<h2 class="card-title text-base">Phone app</h2>
			<p class="text-xs opacity-60">Reporting of this phone (battery, home/away), location permission and logout.</p>
			<button class="btn btn-sm w-fit" onclick={() => phoneApp.openSettings()}>Phone app settings</button>
		</div>
	</div>
{/if}

<div class="card bg-base-100 mb-6 shadow-sm">
	<div class="card-body gap-2 p-4">
		<h2 class="card-title text-base">History</h2>
		<label class="floating-label">
			<span>Keep</span>
			<select class="select select-sm w-full max-w-xs" value={historyDays ?? 0} disabled={historyDays === null}
				onchange={(e) => setHistory(Number(e.currentTarget.value))}>
				<option value={0}>Forever</option>
				<option value={365}>1 year</option>
				<option value={90}>90 days</option>
				<option value={30}>30 days</option>
				<option value={7}>7 days</option>
				<option value={-1}>Off</option>
			</select>
		</label>
		<p class="text-xs opacity-60">State changes and button presses of every device. Shorter settings delete older entries straight away.</p>
	</div>
</div>
