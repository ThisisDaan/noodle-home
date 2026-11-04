<script lang="ts">
	import Icon from '#lib/Icon.svelte';
	import { ago, headline, iconFor, isOn, type Device } from '#lib/api.ts';
	import { groupEditor } from '#lib/groups.svelte.ts';
	import { layout, ui } from '#lib/layout.svelte.ts';
	import { live } from '#lib/live.svelte.ts';

	let query = $state('');
	let source = $state<'all' | 'zigbee' | 'matter' | 'group'>('all');
	let room = $state('all');

	const shown = $derived(
		live.list.filter(
			(d) =>
				(source === 'all' || d.source === source) &&
				(room === 'all' || (room === '' ? d.area === null : d.area === room)) &&
				(d.name + ' ' + (d.model ?? '') + ' ' + (d.manufacturer ?? '') + ' ' + (d.area ?? ''))
					.toLowerCase()
					.includes(query.toLowerCase())
		)
	);

	const view = $derived(layout.devicesView);

	const TYPE_ORDER = ['Lights', 'Plugs and switches', 'Buttons and remotes', 'Sensors', 'Heating', 'Other'];
	function typeOf(d: Device): string {
		const kinds = new Set(d.entities.map((e) => e.kind));
		if (kinds.has('climate')) return 'Heating';
		if (kinds.has('light')) return 'Lights';
		if (kinds.has('switch')) return 'Plugs and switches';
		if (kinds.has('button')) return 'Buttons and remotes';
		if (kinds.has('sensor') || kinds.has('binary_sensor')) return 'Sensors';
		return 'Other';
	}

	const ordered = $derived(
		[...shown].sort(
			view.sort === 'recent' ? (a, b) => (b.last_seen ?? 0) - (a.last_seen ?? 0) : (a, b) => a.name.localeCompare(b.name)
		)
	);

	// Devices under a heading each: per room (in room order, "No room" last), per type, per integration, or all together.
	// Empty groups are left out.
	const groups = $derived.by((): { key: string; title: string | null; devices: Device[] }[] => {
		const make = (key: string, title: string | null, test: (d: Device) => boolean) => ({ key, title, devices: ordered.filter(test) });
		const list =
			view.group_by === 'none'
				? [make('all', null, () => true)]
				: view.group_by === 'type'
					? TYPE_ORDER.map((t) => make(t, t, (d) => typeOf(d) === t))
					: view.group_by === 'source'
						? [...new Set(ordered.map((d) => d.source))].sort().map((s) => make(s, s[0].toUpperCase() + s.slice(1), (d) => d.source === s))
						: [...live.areas, null].map((area) => make(area ?? '~', area ?? 'No room', (d) => d.area === area));
		return list.filter((g) => g.devices.length);
	});
</script>

{#snippet tile(d: Device)}
	<button class="tile flex items-center gap-3 p-3.5 text-left" class:is-on={isOn(d)} class:opacity-60={!d.available}
		onclick={() => ui.open(d.id)} aria-label="Open {d.name}">
		<span class="icon-bubble"><Icon name={iconFor(d)} /></span>
		<span class="min-w-0 grow">
			<span class="block truncate font-semibold">{d.name}</span>
			<span class="block truncate text-sm opacity-70">{headline(d)}</span>
			<span class="block truncate text-xs opacity-50">
				<span class="uppercase">{d.source}</span> · {d.manufacturer ?? ''} {d.model ?? ''} · {ago(d.last_seen)}
			</span>
		</span>
		<span class="flex shrink-0 flex-col items-end gap-1">
			<span class="status" class:status-success={d.available} class:status-error={!d.available}></span>
			{#if d.battery !== null}
				<span class="flex items-center gap-1 text-xs" class:text-warning={d.battery < 20}>
					<Icon name="battery" class="size-4" />{d.battery}%
				</span>
			{/if}
		</span>
	</button>
{/snippet}

<div class="mb-5 flex flex-wrap items-center gap-3">
	<h1 class="mr-auto text-3xl font-bold tracking-tight">
		Devices <span class="text-base font-normal opacity-60">{shown.length}</span>
	</h1>
	<label class="input input-sm w-full sm:w-56">
		<Icon name="search" class="size-4 opacity-60" />
		<input type="search" placeholder="Search devices" bind:value={query} />
	</label>
	<select class="select select-sm w-auto" bind:value={room} aria-label="Room">
		<option value="all">All rooms</option>
		{#each live.areas as a (a)}<option value={a}>{a}</option>{/each}
		<option value="">No room</option>
	</select>
	<select class="select select-sm w-auto" value={view.group_by} aria-label="Group by"
		onchange={(e) => layout.setDevicesView({ group_by: e.currentTarget.value as typeof view.group_by })}>
		<option value="room">Group by room</option>
		<option value="type">Group by type</option>
		<option value="source">Group by integration</option>
		<option value="none">No groups</option>
	</select>
	<select class="select select-sm w-auto" value={view.sort} aria-label="Sort"
		onchange={(e) => layout.setDevicesView({ sort: e.currentTarget.value as typeof view.sort })}>
		<option value="name">Sort by name</option>
		<option value="recent">Recently seen first</option>
	</select>
	<button class="btn btn-sm btn-primary" onclick={() => groupEditor.create()}>
		<Icon name="bulb" class="size-4" />New light group
	</button>
	<div class="join">
		{#each ['all', 'zigbee', 'matter', 'group'] as s (s)}
			<input class="join-item btn btn-sm capitalize" type="radio" name="source" aria-label={s} value={s} bind:group={source} />
		{/each}
	</div>
</div>

{#each groups as g (g.key)}
	<section class="mb-8">
		{#if g.title}
			<h2 class="mb-3 flex items-center gap-2 text-lg font-semibold">
				{g.title} <span class="badge badge-ghost badge-sm">{g.devices.length}</span>
			</h2>
		{/if}
		<div class="grid grid-cols-[repeat(auto-fill,minmax(20rem,1fr))] gap-3">
			{#each g.devices as d (d.id)}{@render tile(d)}{/each}
		</div>
	</section>
{:else}
	<p class="text-sm opacity-60">No devices match.</p>
{/each}
