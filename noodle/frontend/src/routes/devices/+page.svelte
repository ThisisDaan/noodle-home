<script lang="ts">
	import DeviceCard from '#lib/DeviceCard.svelte';
	import AddDevice from '#lib/integrations/AddDevice.svelte';
	import Icon from '#lib/Icon.svelte';
	import type { Device } from '#lib/api.ts';
	import { customEditor } from '#lib/custom.svelte.ts';
	import { groupEditor } from '#lib/groups.svelte.ts';
	import { layout } from '#lib/layout.svelte.ts';
	import { live } from '#lib/live.svelte.ts';

	let query = $state('');
	let source = $state('all');
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

	// The integrations that have devices here, for the filter (not a fixed list).
	const sources = $derived([...new Set(live.list.map((d) => d.source))].sort());
	const sourceLabel = (s: string) => (s === 'group' ? 'Light groups' : s[0].toUpperCase() + s.slice(1));
	const filtered = $derived(query !== '' || room !== 'all' || source !== 'all');
	const reset = () => {
		query = '';
		room = 'all';
		source = 'all';
	};

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
	<DeviceCard device={d} />
{/snippet}

<div class="mb-4 flex items-center gap-3">
	<h1 class="mr-auto min-w-0 truncate text-3xl font-bold tracking-tight">
		Devices <span class="text-base font-normal opacity-60">{shown.length}</span>
	</h1>
	<div class="flex shrink-0 items-center gap-2">
		<button class="btn btn-sm btn-ghost" onclick={() => groupEditor.create()} aria-label="New light group">
			<Icon name="bulb" class="size-4" /><span class="hidden sm:inline">New light group</span><span class="sm:hidden">Group</span>
		</button>
		<button class="btn btn-sm btn-ghost" onclick={() => customEditor.create()} aria-label="New custom device">
			<Icon name="variable" class="size-4" /><span class="hidden sm:inline">New custom device</span><span class="sm:hidden">Custom</span>
		</button>
		<AddDevice />
	</div>
</div>

<div class="mb-6 flex flex-wrap items-center gap-2">
	<label class="input input-sm min-w-48 grow sm:max-w-sm">
		<Icon name="search" class="size-4 opacity-60" />
		<input type="search" placeholder="Search devices" aria-label="Search devices" bind:value={query} />
	</label>
	<select class="select select-sm w-auto" bind:value={room} aria-label="Room">
		<option value="all">All rooms</option>
		{#each live.areas as a (a)}<option value={a}>{a}</option>{/each}
		<option value="">No room</option>
	</select>
	{#if sources.length > 1}
		<select class="select select-sm w-auto" bind:value={source} aria-label="Integration">
			<option value="all">All integrations</option>
			{#each sources as s (s)}<option value={s}>{sourceLabel(s)}</option>{/each}
		</select>
	{/if}
	{#if filtered}
		<button class="btn btn-sm btn-ghost" onclick={reset}>Clear filters</button>
	{/if}
	<details class="dropdown dropdown-end ml-auto">
		<summary class="btn btn-sm btn-ghost"><Icon name="sliders" class="size-4" />View</summary>
		<div class="dropdown-content bg-base-100 border-base-content/10 rounded-box z-10 mt-1 flex w-56 flex-col gap-3 border p-3 shadow-lg">
			<label class="flex flex-col gap-1 text-xs font-medium opacity-80">Group by
				<select class="select select-sm w-full" value={view.group_by}
					onchange={(e) => layout.setDevicesView({ group_by: e.currentTarget.value as typeof view.group_by })}>
					<option value="room">Room</option>
					<option value="type">Type</option>
					<option value="source">Integration</option>
					<option value="none">No groups</option>
				</select>
			</label>
			<label class="flex flex-col gap-1 text-xs font-medium opacity-80">Sort by
				<select class="select select-sm w-full" value={view.sort}
					onchange={(e) => layout.setDevicesView({ sort: e.currentTarget.value as typeof view.sort })}>
					<option value="name">Name</option>
					<option value="recent">Recently seen first</option>
				</select>
			</label>
		</div>
	</details>
</div>

{#each groups as g (g.key)}
	<section class="mb-8">
		{#if g.title}
			<h2 class="mb-3 flex items-center gap-2 text-lg font-semibold">
				{g.title} <span class="badge badge-ghost badge-sm">{g.devices.length}</span>
			</h2>
		{/if}
		<div class="grid auto-rows-[minmax(9rem,auto)] grid-flow-dense grid-cols-2 sm:grid-cols-[repeat(auto-fill,minmax(16rem,1fr))] gap-3">
			{#each g.devices as d (d.id)}{@render tile(d)}{/each}
		</div>
	</section>
{:else}
	<p class="text-sm opacity-60">No devices match.</p>
{/each}
