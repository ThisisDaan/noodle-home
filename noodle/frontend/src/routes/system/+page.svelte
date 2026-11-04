<script lang="ts">
	// Set by the Noodle Android app's WebView, so its settings are reachable from the same interface.
	const phoneApp = typeof window !== 'undefined' ? (window as any).NoodleApp : undefined;
	let z2mUrl = $state('');
	$effect(() => {
		api<{ id: string; fields: { key: string; value: string }[] }[]>('/integrations')
			.then((list) => (z2mUrl = list.find((i) => i.id === 'zigbee')?.fields.find((f) => f.key === 'z2m_url')?.value ?? ''))
			.catch(() => {});
	});
	import { api } from '#lib/api.ts';

	type Container = {
		id: string; name: string; image: string; state: string; status: string;
		ports: string[]; host_network: boolean; web: { scheme: string; port: number } | null;
	};
	type System = {
		docker?: { available: boolean; containers: Container[] };
		zigbee: { connected: boolean; online: boolean; permit_join: boolean; version: string | null };
		matter: {
			connected: boolean; sdk_version?: string; fabric_id?: number; bluetooth_enabled?: boolean;
			thread: { reachable: boolean; state?: string; network_name?: string; channel?: number; routers?: number; error?: string };
		};
	};

	let system = $state<System | null>(null);
	let error = $state('');
	let busy = $state<string | null>(null);
	let logs = $state({ name: '', text: '' });
	let joinLeft = $state(0);
	let logDialog: HTMLDialogElement;

	async function load() {
		try {
			system = await api<System>('/system');
			error = '';
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}

	async function restart(name: string) {
		if (!confirm(`Restart ${name}?`)) return;
		busy = name;
		try {
			await api(`/containers/${name}/restart`, { body: {} });
			await load();
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = null;
		}
	}

	async function showLogs(name: string) {
		logs = { name, text: 'Loading…' };
		logDialog.showModal();
		const res = await api<{ logs: string }>(`/containers/${name}/logs?tail=300`);
		logs = { name, text: res.logs || '(no output)' };
	}

	import { live } from '#lib/live.svelte.ts';
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

	let notifyInfo = $state<{ configured: boolean; server: string; topic: string; app_connections: number } | null>(null);
	let notifyResult = $state('');

	async function testNotify() {
		try {
			const res = await api<{ local: number; ntfy: boolean }>('/notify/test', { body: {} });
			const via = [res.local ? `the Noodle app (${res.local} connected)` : '', res.ntfy ? 'ntfy' : ''].filter(Boolean).join(' and ');
			notifyResult = `Sent through ${via}. It should show up on your phone within a few seconds.`;
		} catch (err) {
			notifyResult = err instanceof Error ? err.message : String(err);
		}
	}

	$effect(() => {
		api<typeof notifyInfo>('/notify').then((info) => (notifyInfo = info));
	});

	let historyDays = $state<number | null>(null);

	$effect(() => {
		api<{ days: number }>('/settings/history').then((s) => (historyDays = s.days));
	});

	async function setHistory(days: number) {
		historyDays = (await api<{ days: number }>('/settings/history', { method: 'PUT', body: { days } })).days;
	}

	let matterCode = $state('');
	let pairing = $state(false);
	let pairResult = $state('');

	async function pairMatter(e: SubmitEvent) {
		e.preventDefault();
		pairing = true;
		pairResult = 'Pairing… keep the device close to the Pi.';
		try {
			const res = await api<{ device_id: string }>('/matter/commission', { body: { code: matterCode } });
			pairResult = `Paired as ${res.device_id}. Give it a name and room under Devices.`;
			matterCode = '';
		} catch (err) {
			pairResult = err instanceof Error ? err.message : String(err);
		} finally {
			pairing = false;
		}
	}

	async function permitJoin(seconds: number) {
		await api('/zigbee/permit_join', { body: { seconds } });
		joinLeft = seconds;
	}

	$effect(() => {
		// Loaded when the page opens and after each action here; the Refresh button checks again.
		load();
		const tick = setInterval(() => (joinLeft = Math.max(0, joinLeft - 1)), 1000);
		return () => clearInterval(tick);
	});
</script>

<div class="mb-4 flex items-center justify-between gap-3">
	<h1 class="text-2xl font-bold">System</h1>
	<button class="btn btn-sm" onclick={load}>Refresh</button>
</div>
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
{#if error}<div role="alert" class="alert alert-error alert-soft mb-4">{error}</div>{/if}

{#if !system}
	<div class="flex justify-center py-20"><span class="loading loading-dots loading-lg"></span></div>
{:else}
	<div class="mb-6 grid gap-3 md:grid-cols-3">
		<div class="card bg-base-100 shadow-sm">
			<div class="card-body gap-2 p-4">
				<h2 class="card-title text-base">
					<span class="status" class:status-success={system.zigbee.connected && system.zigbee.online} class:status-error={!system.zigbee.online}></span>
					Zigbee
				</h2>
				<p class="text-sm opacity-70">Zigbee2MQTT {system.zigbee.version ?? '?'} · {system.zigbee.online ? 'online' : 'offline'}</p>
				{#if joinLeft > 0}
					<button class="btn btn-warning btn-sm" onclick={() => permitJoin(0)}>Pairing open · {joinLeft}s · stop</button>
				{:else}
					<button class="btn btn-sm" onclick={() => permitJoin(60)} disabled={!system.zigbee.online}>Pair Zigbee device (60s)</button>
					<a class="btn btn-sm btn-outline" href={z2mUrl || `${location.protocol}//${location.hostname}:8081`} target="_blank" rel="noopener">Open Zigbee2MQTT</a>
				{/if}
			</div>
		</div>
		<div class="card bg-base-100 shadow-sm">
			<div class="card-body gap-2 p-4">
				<h2 class="card-title text-base">
					<span class="status" class:status-success={system.matter.connected} class:status-error={!system.matter.connected}></span>
					Matter
				</h2>
				<p class="text-sm opacity-70">
					{system.matter.connected ? `matter-server · SDK ${system.matter.sdk_version}` : 'matter-server not reachable'}
				</p>
				{#if system.matter.bluetooth_enabled}
					<form class="join w-full" onsubmit={pairMatter}>
						<input class="input input-sm join-item grow" placeholder="QR text (MT:…) or 11-digit code" bind:value={matterCode} disabled={pairing} />
						<button class="btn btn-sm btn-primary join-item" disabled={pairing || matterCode.length < 11}>
							{#if pairing}<span class="loading loading-spinner loading-xs"></span>{/if}Pair
						</button>
					</form>
					<p class="text-xs opacity-60">Hold the device within a few metres of the Pi. Pairing takes up to a few minutes.</p>
					{#if pairResult}<p class="text-xs" class:text-error={pairResult.startsWith('Pairing failed')}>{pairResult}</p>{/if}
				{:else}
					<p class="text-sm opacity-70">Bluetooth pairing is off in matter-server.</p>
				{/if}
			</div>
		</div>
		<div class="card bg-base-100 shadow-sm">
			<div class="card-body gap-2 p-4">
				<h2 class="card-title text-base">
					<span class="status" class:status-success={system.matter.thread.reachable && system.matter.thread.state === 'leader'}
						class:status-warning={system.matter.thread.reachable && system.matter.thread.state !== 'leader'}
						class:status-error={!system.matter.thread.reachable}></span>
					Thread
				</h2>
				{#if system.matter.thread.reachable}
					<p class="text-sm opacity-70">{system.matter.thread.network_name} · channel {system.matter.thread.channel}</p>
					<p class="text-sm opacity-70">Border router: {system.matter.thread.state} · {system.matter.thread.routers} routers</p>
				{:else}
					<p class="text-sm opacity-70">Border router not reachable</p>
				{/if}
			</div>
		</div>
	</div>

	<div class="card bg-base-100 mb-6 shadow-sm">
		<div class="card-body gap-2 p-4">
			<h2 class="card-title text-base">
				<span class="status" class:status-success={notifyInfo?.configured || notifyInfo?.app_connections} class:status-error={!notifyInfo?.configured && !notifyInfo?.app_connections}></span>
				Notifications
			</h2>
			<p class="text-sm">
				<b>Noodle app (home network):</b>
				{#if notifyInfo?.app_connections}
					{notifyInfo.app_connections} phone{notifyInfo.app_connections > 1 ? 's' : ''} connected. Works without internet.
				{:else}
					<span class="opacity-70">no phone connected. Open the Noodle app and turn on Settings › Notifications on this network.</span>
				{/if}
			</p>
			<p class="text-sm"><b>ntfy (anywhere):</b>
				{#if !notifyInfo?.configured}<span class="opacity-70">off. Add it under Integrations to turn it on.</span>{/if}
			</p>
			{#if notifyInfo?.configured}
				<p class="text-sm opacity-70">Install the <b>ntfy</b> app, tap +, and subscribe to this topic on server <code>{notifyInfo.server}</code>. Keep the name secret: anyone who knows it can read along.</p>
				<div class="join">
					<input class="input input-sm join-item grow font-mono" readonly value={notifyInfo.topic} aria-label="ntfy topic" />
					<button class="btn btn-sm join-item" onclick={() => navigator.clipboard?.writeText(notifyInfo!.topic)}>Copy</button>
				</div>
			{/if}
			{#if notifyInfo?.configured || notifyInfo?.app_connections}
				<button class="btn btn-sm btn-primary w-fit" onclick={testNotify}>Send test</button>
			{/if}
			{#if notifyResult}<p class="text-xs">{notifyResult}</p>{/if}
		</div>
	</div>

	{#if phoneApp}
		<div class="card bg-base-100 mb-6 shadow-sm">
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

	{#if system.docker?.available}
		<h2 class="mb-2 text-lg font-bold">Containers</h2>
		<div class="bg-base-100 overflow-x-auto rounded-box shadow-sm">
			<table class="table table-sm">
				<thead><tr><th>Name</th><th class="hidden md:table-cell">Image</th><th>Ports</th><th>Status</th><th></th></tr></thead>
				<tbody>
					{#each system.docker.containers as c (c.id)}
						<tr>
							<td class="font-medium">
								<span class="status mr-1" class:status-success={c.state === 'running'} class:status-error={c.state !== 'running'}></span>
								{c.name}
							</td>
							<td class="hidden max-w-xs truncate text-xs opacity-70 md:table-cell">{c.image}</td>
							<td class="text-xs">
								{#if c.ports.length}{c.ports.join(', ')}{:else if c.host_network}<span class="opacity-60">host network</span>{:else}–{/if}
							</td>
							<td class="text-xs">{c.status}</td>
							<td class="flex justify-end gap-1">
								{#if c.web}
									<a class="btn btn-ghost btn-xs" href="{c.web.scheme}://{location.hostname}:{c.web.port}" target="_blank" rel="noopener">Open</a>
								{/if}
								<button class="btn btn-ghost btn-xs" onclick={() => showLogs(c.name)}>Logs</button>
								<button class="btn btn-ghost btn-xs" disabled={busy === c.name} onclick={() => restart(c.name)}>
									{#if busy === c.name}<span class="loading loading-spinner loading-xs"></span>{/if}
									Restart
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
{/if}

<dialog class="modal" bind:this={logDialog}>
	<div class="modal-box w-11/12 max-w-5xl">
		<h3 class="mb-2 text-lg font-bold">{logs.name}</h3>
		<pre class="bg-base-200 max-h-[70vh] overflow-auto rounded p-3 text-xs whitespace-pre-wrap">{logs.text}</pre>
		<div class="modal-action"><button class="btn" onclick={() => logDialog.close()}>Close</button></div>
	</div>
	<form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>
