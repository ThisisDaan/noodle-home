<script lang="ts">
	import EntityControl from './EntityControl.svelte';
	import HistoryChart from './HistoryChart.svelte';
	import Icon from './Icon.svelte';
	import DeviceFace from './devices/DeviceFace.svelte';
	import { faceEntities, sheetFace } from './devices/kinds.ts';
	import { ago, api, controllable, formatState, headline, iconFor, isOn } from './api';
	import { cardDesigner } from './designer.svelte';
	import { combineEditor } from './combine.svelte';
	import { customEditor } from './custom.svelte';
	import { groupEditor } from './groups.svelte';
	import { layout, ui } from './layout.svelte';
	import { live, type HistoryRow } from './live.svelte';

	// The Zigbee2MQTT web UI: the address set on the Integrations page, else port 8081 of the machine you are browsing to.
	let z2mUrl = $state('');
	$effect(() => {
		api<{ id: string; fields: { key: string; value: string }[] }[]>('/integrations')
			.then((list) => (z2mUrl = list.find((i) => i.id === 'zigbee')?.fields.find((f) => f.key === 'z2m_url')?.value ?? ''))
			.catch(() => {});
	});
	const z2m = (id: string, tab: string) =>
		`${z2mUrl || `${location.protocol}//${location.hostname}:8081`}/#/device/${id.split(':')[1]}/${tab}`;

	let dialog: HTMLDialogElement;
	let name = $state('');
	let area = $state('');
	let newArea = $state('');
	let presence = $state(5);
	let error = $state('');
	let saved = $state(false);
	let loadedId: string | null = null;

	const device = $derived(ui.selected ? live.devices[ui.selected] : undefined);
	const controls = $derived(device?.entities.filter(controllable) ?? []);
	// What the face at the top already shows is left out of the lists below; battery, the device's own temperature
	// and the rest stay there as properties.
	const faced = $derived(new Set(device ? faceEntities(device).map((e) => e.key) : []));
	const hasFace = $derived(!!device && sheetFace(device));
	const readings = $derived(device?.entities.filter((e) => !controllable(e) && e.kind !== 'button' && !faced.has(e.key)) ?? []);
	const buttons = $derived(device?.entities.filter((e) => e.kind === 'button' && e.state !== null && !faced.has(e.key)) ?? []);
	const dirty = $derived(
		!!device && (name.trim() !== device.name || (area || null) !== device.area || newArea.trim() !== '' ||
			(device.presence_minutes !== null && presence !== device.presence_minutes))
	);

	// Open/close the dialog and reset the form when a different device is picked.
	$effect(() => {
		if (device && loadedId !== device.id) {
			loadedId = device.id;
			name = device.name;
			area = device.area ?? '';
			newArea = '';
			presence = device.presence_minutes ?? 5;
			error = '';
			saved = false;
		}
		if (device && !dialog.open) dialog.showModal();
		if (!device) {
			loadedId = null;
			if (dialog?.open) dialog.close();
		}
	});

	type Row = { ts: number; key: string; value: boolean | number | string | null };
	let history = $state<Row[]>([]);

	// Fetched once when a device is opened; after that new rows arrive over the websocket (see below).
	$effect(() => {
		const id = ui.selected;
		history = [];
		if (!id) return;
		api<Row[]>(`/devices/${encodeURIComponent(id)}/history?limit=100`).then((rows) => {
			if (ui.selected === id) history = rows;
		}).catch(() => {});
	});

	// The graph: everything in the chosen time range.
	const RANGES = [['1h', 3600], ['24h', 86400], ['7d', 7 * 86400], ['30d', 30 * 86400]] as const;
	let range = $state<number>(86400);
	// How long one block of the graph is, in seconds; 0 picks a size that gives about 48 blocks.
	const BLOCKS = [60, 300, 900, 1800, 3600, 10800, 21600, 86400];
	let block = $state(0);
	const blockOptions = $derived(BLOCKS.filter((b) => range / b >= 2 && range / b <= 300));
	const blockSize = $derived(blockOptions.includes(block) ? block : (blockOptions.find((b) => range / b <= 60) ?? blockOptions[blockOptions.length - 1] ?? 300));
	const blockName = (b: number) => (b >= 86400 ? `${b / 86400} day` : b >= 3600 ? `${b / 3600} hour${b > 3600 ? 's' : ''}` : `${b / 60} min`);
	let chart = $state<{ rows: Row[]; from: number; to: number }>({ rows: [], from: 0, to: 1 });

	// Fetched when a device or range is picked.
	$effect(() => {
		const id = ui.selected;
		const span = range;
		chart = { rows: [], from: 0, to: 1 };
		if (!id) return;
		const to = Date.now() / 1000, from = to - span;
		api<Row[]>(`/devices/${encodeURIComponent(id)}/history?limit=5000&since=${from}`).then((rows) => {
			if (ui.selected === id) chart = { rows, from, to };
		}).catch(() => {});
	});

	// Rows the server pushes: add them to the list and the graph (newest first, like the fetched ones).
	$effect(() => {
		const onRow = (r: HistoryRow) => {
			if (r.device_id !== ui.selected) return;
			const row: Row = { ts: r.ts, key: r.key, value: r.value };
			history = [row, ...history].slice(0, 100);
			if (chart.to > 1) chart = { rows: [row, ...chart.rows], from: r.ts - range, to: r.ts };
		};
		live.historyListeners.add(onRow);
		return () => live.historyListeners.delete(onRow);
	});

	function describe(row: Row): string {
		const entity = device?.entities.find((e) => e.key === row.key);
		if (!entity) return `${row.key}: ${row.value}`;
		const value = entity.kind === 'button' ? String(row.value).replaceAll('_', ' ') : formatState({ ...entity, state: row.value });
		return entity.kind === 'button' || device!.entities.length === 1 ? value : `${entity.name}: ${value}`;
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		if (!device) return;
		error = '';
		try {
			let room = area;
			if (newArea.trim()) {
				live.areas = await api<string[]>('/areas', { body: { name: newArea.trim() } });
				room = newArea.trim();
				area = room;
				newArea = '';
			}
			await api(`/devices/${encodeURIComponent(device.id)}`, {
				method: 'PUT',
				body: { name: name.trim() || null, area: room || null, presence_minutes: device.presence_minutes !== null ? presence : null }
			});
			saved = true;
			setTimeout(() => (saved = false), 1800);
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}
</script>

<dialog class="modal modal-bottom sm:modal-end" bind:this={dialog} onclose={() => ui.close()}>
	<div class="modal-box sheet-box flex flex-col gap-5 overflow-y-auto p-0">
		{#if device}
			<header class="bg-base-100 sticky top-0 z-10 flex items-center gap-3 p-4 pb-3" class:is-on={isOn(device)}>
				<span class="icon-bubble size-12 {isOn(device) ? 'bg-accent text-accent-content' : ''}">
					<Icon name={iconFor(device)} class="size-6" />
				</span>
				<div class="min-w-0 grow">
					<h2 class="truncate text-lg leading-tight font-bold">{device.name}</h2>
					<p class="truncate text-sm opacity-70">{device.area ?? 'No room'} · {headline(device)}</p>
				</div>
				<button
					class="btn btn-ghost btn-sm btn-circle"
					class:text-accent={layout.isFavorite(device.id)}
					aria-label="Pin to favourites"
					onclick={() => layout.toggleFavorite(device.id)}
				>
					<Icon name="star" class="size-5 {layout.isFavorite(device.id) ? 'fill-current' : ''}" />
				</button>
				<form method="dialog">
					<button class="btn btn-ghost btn-sm btn-circle" aria-label="Close"><Icon name="close" /></button>
				</form>
			</header>

			<div class="flex flex-col gap-5 px-4 pb-6">
				{#if !device.available}
					<div role="alert" class="alert alert-error alert-soft text-sm">
						<Icon name="wifi" class="size-5" />
						<span>This device is offline. Last seen {ago(device.last_seen)}.</span>
					</div>
				{/if}

				{#if hasFace}<DeviceFace {device} size="large" />{/if}

				{#if controls.length}
					<section class="flex flex-col gap-3">
						<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">Controls</h3>
						{#each controls as entity (entity.key)}
							<div class="bg-base-200 rounded-box p-3.5"><EntityControl {device} {entity} /></div>
						{/each}
					</section>
				{/if}

				{#if readings.length || buttons.length}
					<section class="flex flex-col gap-2">
						<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">{hasFace ? 'Properties' : 'Readings'}</h3>
						<div class="bg-base-200 rounded-box flex flex-col gap-2.5 p-3.5">
							{#each readings as entity (entity.key)}<EntityControl {device} {entity} />{/each}
							{#each buttons as entity (entity.key)}<EntityControl {device} {entity} />{/each}
						</div>
					</section>
				{/if}

				{#if device.source === 'zigbee'}
					<section class="flex flex-col gap-2">
						<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">Zigbee2MQTT</h3>
						<p class="text-xs opacity-60">Advanced settings: reporting, binding, firmware update, remove or re-pair.</p>
						<div class="grid grid-cols-2 gap-2">
							{#each [['settings', 'Settings'], ['bind', 'Binding'], ['reporting', 'Reporting'], ['exposes', 'Exposes']] as [tab, label] (tab)}
								<a class="btn btn-outline btn-sm" href={z2m(device.id, tab)} target="_blank" rel="noopener">{label}</a>
							{/each}
						</div>
					</section>
				{/if}

				<section class="flex flex-col gap-2">
					<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">Card</h3>
					<button class="btn btn-outline" onclick={() => { const id = device.id; ui.close(); cardDesigner.open(id); }}>
						{layout.cards[device.id] ? 'Change the card design' : 'Design the card'}
					</button>
				</section>
				{#if device.source === 'custom'}
					<section class="flex flex-col gap-2">
						<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">Made by you</h3>
						<button class="btn btn-outline" onclick={() => { const id = device.id.split(':')[1]; ui.close(); customEditor.edit(id); }}>
							Edit (name and fields)
						</button>
					</section>
				{/if}
				{#if device.source === 'combined'}
					<section class="flex flex-col gap-2">
						<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">Made from other devices</h3>
						<button class="btn btn-outline" onclick={() => { const id = device.id.split(':')[1]; ui.close(); combineEditor.edit(id); }}>
							Edit (sensor, plug and limits)
						</button>
					</section>
				{/if}
				{#if device.source === 'group'}
					<section class="flex flex-col gap-2">
						<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">Lamps in this group</h3>
						<button class="btn btn-outline" onclick={() => { const id = device.id.split(':')[1]; ui.close(); groupEditor.edit(id); }}>
							Edit group (name and lamps)
						</button>
					</section>
				{/if}

				<form class="flex flex-col gap-3" onsubmit={save}>
					<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">{device.presence_minutes !== null ? 'Name, room and presence' : 'Name and room'}</h3>
					<label class="floating-label">
						<span>Name</span>
						<input class="input w-full" bind:value={name} placeholder="Name" />
					</label>
					<label class="floating-label">
						<span>Room</span>
						<select class="select w-full" bind:value={area}>
							<option value="">No room</option>
							{#each live.areas as a (a)}<option value={a}>{a}</option>{/each}
						</select>
					</label>
					<label class="floating-label">
						<span>Or create a new room</span>
						<input class="input w-full" bind:value={newArea} placeholder="Or create a new room" />
					</label>
					{#if device.presence_minutes !== null}
						<label class="floating-label">
							<span>Presence: minutes without motion before the room counts as empty</span>
							<input class="input w-full" type="number" min="0.5" max="1440" step="0.5" bind:value={presence} />
						</label>
						<p class="text-xs opacity-60">
							"Presence" turns on with motion and stays on until there was no motion for this many minutes. Use it in
							automations instead of motion plus a timer.
						</p>
					{/if}
					{#if error}<div role="alert" class="alert alert-error alert-soft text-sm">{error}</div>{/if}
					<button class="btn btn-primary" disabled={!dirty && !saved}>
						{#if saved}<Icon name="check" class="size-5" />Saved{:else}Save changes{/if}
					</button>
				</form>

				{#if history.length}
					<section class="flex flex-col gap-2">
						<div class="flex items-center justify-between">
							<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">Graph</h3>
							<div class="join">
								{#each RANGES as [label, seconds] (label)}
									<button class="btn btn-xs join-item" class:btn-active={range === seconds} onclick={() => (range = seconds)}>{label}</button>
								{/each}
							</div>
						</div>
						<label class="flex items-center gap-2 text-xs">
							<span class="opacity-60">Block size</span>
							<select class="select select-xs w-auto" value={blockSize} onchange={(e) => (block = Number(e.currentTarget.value))}>
								{#each blockOptions as b (b)}<option value={b}>{blockName(b)}</option>{/each}
							</select>
						</label>
						<HistoryChart {device} rows={chart.rows} from={chart.from} to={chart.to} size={blockSize} />
					</section>
					<section class="flex flex-col gap-2">
						<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">History</h3>
						<ul class="bg-base-200 rounded-box max-h-64 overflow-y-auto p-3.5 text-sm">
							{#each history as row (row.ts + row.key)}
								<li class="flex justify-between gap-3 py-0.5">
									<span>{describe(row)}</span>
									<span class="shrink-0 opacity-60">{new Date(row.ts * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
								</li>
							{/each}
						</ul>
					</section>
				{/if}

				<section class="flex flex-col gap-2">
					<h3 class="text-xs font-semibold tracking-wide uppercase opacity-60">Details</h3>
					<dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
						<dt class="opacity-60">Source</dt><dd class="capitalize">{device.source}</dd>
						{#if device.manufacturer}<dt class="opacity-60">Maker</dt><dd>{device.manufacturer}</dd>{/if}
						{#if device.model}<dt class="opacity-60">Model</dt><dd>{device.model}</dd>{/if}
						{#if device.battery !== null}<dt class="opacity-60">Battery</dt><dd>{device.battery}%</dd>{/if}
						<dt class="opacity-60">Last seen</dt><dd>{ago(device.last_seen)}</dd>
						<dt class="opacity-60">ID</dt><dd class="font-mono text-xs break-all">{device.id}</dd>
					</dl>
				</section>
			</div>
		{/if}
	</div>
	<form method="dialog" class="modal-backdrop"><button aria-label="Close">close</button></form>
</dialog>
