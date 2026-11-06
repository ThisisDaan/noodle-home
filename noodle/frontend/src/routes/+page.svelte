<script lang="ts">
	import DeviceCard from '#lib/DeviceCard.svelte';
	import FlowCard from '#lib/FlowCard.svelte';
	import Icon from '#lib/Icon.svelte';
	import { ago, api, command, iconFor, type Device } from '#lib/api.ts';
	import { layout, type Widget } from '#lib/layout.svelte.ts';
	import SensorWidget from '#lib/SensorWidget.svelte';
	import { live } from '#lib/live.svelte.ts';

	// Loaded once; a flow setting a variable pushes the new values.
	// The values of card controls are variables too ("<flow>.<control>"), but they belong to their card.
	const controlVars = $derived(new Set((live.flows ?? []).flatMap((f) => (f.card?.controls ?? []).map((c) => `${f.id}.${c.id}`))));
	const vars = $derived(Object.fromEntries(Object.entries(live.variables ?? {}).filter(([name]) => !controlVars.has(name))));
	$effect(() => {
		api<typeof vars>('/variables').then((v) => (live.variables = v)).catch(() => {});
	});

	const widgets = $derived(layout.activeWidgets);
	const WIDGET_NAMES: Record<Widget['type'], string> = {
		status: 'Status', favourites: 'Favourites', rooms: 'Rooms', flows: 'Quick actions', sensor: 'Sensor'
	};
	const manualFlows = $derived((live.flows ?? []).filter((f) => f.manual));
	let newSensor = $state('');
	const sensorChoices = $derived(
		live.list.flatMap((d) =>
			d.entities.filter((e) => e.kind === 'sensor' && typeof e.state === 'number' && e.device_class !== 'device_temperature')
				.map((e) => ({ value: `${d.id}|${e.key}`, label: `${d.name} · ${e.name}` }))
		).sort((a, b) => a.label.localeCompare(b.label))
	);
	const has = (type: Widget['type']) => widgets.some((w) => w.type === type);

	// The flow list is loaded once (like on the Automations page), then the server pushes changes.
	$effect(() => {
		if (!live.flows) api<typeof live.flows>('/flows').then((f) => (live.flows ??= f)).catch(() => {});
	});
	// Cards that flows put on the dashboard (the `card:` of a flow file).
	const cardFlows = $derived((live.flows ?? []).filter((f) => f.card));

	function addSensor() {
		const [device_id, key] = newSensor.split('|');
		if (device_id && key) layout.addWidget({ type: 'sensor', device_id, key, hours: 24 });
		newSensor = '';
	}

	async function runFlow(id: string) {
		await api(`/flows/${id}/run`, { body: {} }).catch(() => {});
	}

	let dragId: string | null = null;
	const editing = $derived(layout.editing);

	const visible = (d: Device) => editing || !layout.isHidden(d.id);
	const favorites = $derived(layout.sorted(live.list.filter((d) => layout.isFavorite(d.id) && visible(d))));
	const hiddenDevices = $derived(live.list.filter((d) => layout.isHidden(d.id)));
	const rooms = $derived(
		layout
			.sortedRooms([...live.areas, null])
			.map((area) => ({ area, devices: layout.sorted(live.list.filter((d) => d.area === area && visible(d))) }))
			.filter((r) => r.devices.length > 0 || (editing && r.area !== null))
	);
	const roomNames = $derived(rooms.flatMap((r) => (r.area === null ? [] : [r.area])));

	const lightsIn = (devices: Device[]) =>
		devices.filter((d) => d.available).flatMap((d) => d.entities.filter((e) => e.kind === 'light').map((e) => ({ d, e })));

	async function allLights(devices: Device[], on: boolean) {
		await Promise.allSettled(lightsIn(devices).map(({ d, e }) => command(d, e, { on })));
	}

	const lightsOnCount = $derived(lightsIn(live.list).filter(({ e }) => e.state === true).length);
	const offlineCount = $derived(live.list.filter((d) => !d.available).length);
	const lowBattery = $derived(live.list.filter((d) => d.battery !== null && d.battery < 20).length);

	const greeting = $derived.by(() => {
		const h = new Date().getHours();
		return h < 5 ? 'Good night' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
	});

	/** Drop the dragged tile onto `target` (or at the end of `area` when null), moving rooms if needed. */
	async function drop(area: string | null, targetId: string | null, siblings: Device[]) {
		const id = dragId;
		dragId = null;
		if (!id) return;
		const dragged = live.devices[id];
		if (dragged && dragged.area !== area) {
			await api(`/devices/${encodeURIComponent(id)}`, { method: 'PUT', body: { name: dragged.name, area } }).catch(() => {});
		}
		layout.place(id, targetId, siblings.map((d) => d.id));
	}
</script>

<div class="mb-6 flex flex-wrap items-end justify-between gap-3">
	<div>
		<h1 class="text-3xl font-bold tracking-tight">{greeting}</h1>
		<p class="opacity-70">
			{#if lightsOnCount}{lightsOnCount} light{lightsOnCount === 1 ? '' : 's'} on{:else}All lights are off{/if}
			{#if offlineCount} · <span class="text-error">{offlineCount} offline</span>{/if}
			{#if lowBattery} · <span class="text-warning">{lowBattery} low battery</span>{/if}
		</p>
	</div>
	<div class="flex items-center gap-2">
		{#if editing}
			<span class="text-sm opacity-60">{layout.saving ? 'Saving…' : 'Saved'}</span>
			<button class="btn btn-primary btn-sm" onclick={() => (layout.editing = false)}>
				<Icon name="check" class="size-4" />Done
			</button>
		{:else}
			<button class="btn btn-sm" onclick={() => (layout.editing = true)}>
				<Icon name="edit" class="size-4" />Edit dashboard
			</button>
		{/if}
	</div>
</div>

{#if editing}
	<div role="status" class="alert alert-info alert-soft mb-6 text-sm">
		<Icon name="edit" class="size-5" />
		<span>Drag tiles to reorder or drop them into another room. On touch, use the arrows. Pin tiles with the star, hide ones you do not need.</span>
	</div>
{/if}

{#snippet statusBlock()}
{#if Object.keys(vars).length}
	<section class="mb-8" aria-label="Status">
		<div class="flex flex-wrap gap-2">
			{#each Object.entries(vars) as [name, v] (name)}
				<div class="bg-base-100 border-base-content/10 rounded-field flex items-baseline gap-2 border px-3 py-1.5 text-sm" title="updated {ago(v.updated)}">
					<span class="opacity-60">{name}</span><b>{v.value || '–'}</b>
				</div>
			{/each}
		</div>
	</section>
{/if}
{/snippet}

{#snippet favouritesBlock()}
{#if favorites.length}
	<section class="mb-10">
		<h2 class="mb-3 flex items-center gap-2 text-lg font-semibold"><Icon name="star" class="text-accent size-5 fill-current" />Favourites</h2>
		<div class="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-3">
			{#each favorites as device, i (device.id)}
				<DeviceCard {device} {editing} first={i === 0} last={i === favorites.length - 1}
					onnudge={(d) => layout.nudge(device.id, d, favorites.map((x) => x.id))}
					ondragstart={() => (dragId = device.id)}
					ondrop={() => drop(device.area, device.id, favorites)} />
			{/each}
		</div>
	</section>
{/if}
{/snippet}

{#snippet roomsBlock()}
{#each rooms as room (room.area ?? '~')}
	{@const lights = lightsIn(room.devices)}
	{@const anyOn = lights.some(({ e }) => e.state === true)}
	<section class="mb-10">
		<div class="mb-3 flex items-center gap-2">
			<h2 class="text-lg font-semibold">{room.area ?? 'No room'}</h2>
			<span class="badge badge-ghost badge-sm">{room.devices.length}</span>
			<span class="grow"></span>
			{#if editing && room.area !== null}
				<button class="btn btn-ghost btn-xs btn-square" aria-label="Move room up"
					disabled={roomNames.indexOf(room.area) === 0} onclick={() => layout.nudgeRoom(room.area!, -1, roomNames)}>
					<Icon name="up" class="size-4" />
				</button>
				<button class="btn btn-ghost btn-xs btn-square" aria-label="Move room down"
					disabled={roomNames.indexOf(room.area) === roomNames.length - 1} onclick={() => layout.nudgeRoom(room.area!, 1, roomNames)}>
					<Icon name="down" class="size-4" />
				</button>
			{:else if lights.length}
				<button class="btn btn-sm btn-soft" onclick={() => allLights(room.devices, !anyOn)}>
					<Icon name="bulb" class="size-4" />{anyOn ? 'All off' : 'All on'}
				</button>
			{/if}
		</div>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-3"
			class:min-h-28={editing}
			ondragover={(e) => editing && e.preventDefault()}
			ondrop={(e) => {
				if (e.target === e.currentTarget) drop(room.area, null, room.devices);
			}}
		>
			{#each room.devices as device, i (device.id)}
				<div class:opacity-40={layout.isHidden(device.id)}>
					<DeviceCard {device} {editing} first={i === 0} last={i === room.devices.length - 1}
						onnudge={(d) => layout.nudge(device.id, d, room.devices.map((x) => x.id))}
						ondragstart={() => (dragId = device.id)}
						ondrop={() => drop(room.area, device.id, room.devices)} />
				</div>
			{:else}
				<p class="text-sm opacity-60">Drop devices here.</p>
			{/each}
		</div>
	</section>
{/each}

{#if editing && hiddenDevices.length}
	<section class="mb-10">
		<h2 class="mb-3 flex items-center gap-2 text-lg font-semibold"><Icon name="eyeoff" class="size-5" />Hidden ({hiddenDevices.length})</h2>
		<div class="flex flex-wrap gap-2">
			{#each hiddenDevices as d (d.id)}
				<button class="btn btn-sm btn-soft" onclick={() => layout.toggleHidden(d.id)}>
					<Icon name={iconFor(d)} class="size-4" />{d.name}<Icon name="eye" class="size-4" />
				</button>
			{/each}
		</div>
	</section>
{/if}
{/snippet}

{#snippet flowsBlock(w: Widget)}
	<section class="mb-8" aria-label="Quick actions">
		<h2 class="mb-3 text-lg font-semibold">{w.title || 'Quick actions'}</h2>
		<div class="flex flex-wrap gap-2">
			{#each manualFlows as f (f.id)}
				<button class="btn btn-sm btn-soft" onclick={() => runFlow(f.id)}><Icon name="bolt" class="size-4" />{f.name}</button>
			{:else}
				<p class="text-sm opacity-60">No flow has a "Run button" trigger yet. Add one in an automation and it shows up here.</p>
			{/each}
		</div>
	</section>
{/snippet}

{#if live.list.length === 0}
	<div class="flex justify-center py-20"><span class="loading loading-dots loading-lg text-primary"></span></div>
{/if}

{#each widgets as w, i (i)}
	<div class="relative">
		{#if editing}
			<div class="bg-base-200 rounded-field mb-3 flex items-center gap-1 px-3 py-1.5 text-sm">
				<span class="grow font-medium">{WIDGET_NAMES[w.type]}</span>
				<button class="btn btn-ghost btn-xs btn-square" aria-label="Move up" disabled={i === 0} onclick={() => layout.moveWidget(i, -1)}><Icon name="up" class="size-4" /></button>
				<button class="btn btn-ghost btn-xs btn-square" aria-label="Move down" disabled={i === widgets.length - 1} onclick={() => layout.moveWidget(i, 1)}><Icon name="down" class="size-4" /></button>
				<button class="btn btn-ghost btn-xs btn-square text-error" aria-label="Remove card" onclick={() => layout.removeWidget(i)}><Icon name="close" class="size-4" /></button>
			</div>
		{/if}
		{#if w.type === 'status'}{@render statusBlock()}
		{:else if w.type === 'favourites'}{@render favouritesBlock()}
		{:else if w.type === 'rooms'}{@render roomsBlock()}
		{:else if w.type === 'flows'}{@render flowsBlock(w)}
		{:else if w.type === 'sensor' && w.device_id && w.key}
			<div class="mb-8 max-w-md"><SensorWidget device_id={w.device_id} key={w.key} title={w.title} hours={w.hours} /></div>
		{/if}
	</div>
{/each}

{#each cardFlows as f (f.id)}<FlowCard flow={f} />{/each}

{#if editing}
	<section class="bg-base-100 border-base-content/10 rounded-box mb-10 border p-4" aria-label="Add a card">
		<h2 class="mb-3 font-semibold">Add a card</h2>
		<div class="flex flex-wrap items-center gap-2">
			{#each ['status', 'favourites', 'rooms'] as type (type)}
				<button class="btn btn-sm btn-soft" disabled={has(type as Widget['type'])} onclick={() => layout.addWidget({ type: type as Widget['type'] })}>
					<Icon name="plus" class="size-4" />{WIDGET_NAMES[type as Widget['type']]}
				</button>
			{/each}
			<button class="btn btn-sm btn-soft" onclick={() => layout.addWidget({ type: 'flows' })}><Icon name="plus" class="size-4" />Quick actions</button>
			<select class="select select-sm w-56" bind:value={newSensor} aria-label="Sensor">
				<option value="">A sensor with a graph…</option>
				{#each sensorChoices as c (c.value)}<option value={c.value}>{c.label}</option>{/each}
			</select>
			<button class="btn btn-sm btn-soft" disabled={!newSensor} onclick={addSensor}><Icon name="plus" class="size-4" />Sensor</button>
		</div>
	</section>
{/if}
