<script lang="ts">
	import Icon from '#lib/Icon.svelte';
	import { ago, headline, iconFor, isOn, type Device } from '#lib/api.ts';
	import { groupEditor } from '#lib/groups.svelte.ts';
	import { ui } from '#lib/layout.svelte.ts';
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

	// Devices under a heading per room, in room order, "No room" last; empty rooms are left out.
	const groups = $derived(
		[...live.areas, null]
			.map((area) => ({ area, devices: shown.filter((d) => d.area === area) }))
			.filter((g) => g.devices.length)
	);
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
	<button class="btn btn-sm btn-primary" onclick={() => groupEditor.create()}>
		<Icon name="bulb" class="size-4" />New light group
	</button>
	<div class="join">
		{#each ['all', 'zigbee', 'matter', 'group'] as s (s)}
			<input class="join-item btn btn-sm capitalize" type="radio" name="source" aria-label={s} value={s} bind:group={source} />
		{/each}
	</div>
</div>

{#each groups as g (g.area ?? '~')}
	<section class="mb-8">
		<h2 class="mb-3 flex items-center gap-2 text-lg font-semibold">
			{g.area ?? 'No room'} <span class="badge badge-ghost badge-sm">{g.devices.length}</span>
		</h2>
		<div class="grid grid-cols-[repeat(auto-fill,minmax(20rem,1fr))] gap-3">
			{#each g.devices as d (d.id)}{@render tile(d)}{/each}
		</div>
	</section>
{:else}
	<p class="text-sm opacity-60">No devices match.</p>
{/each}
