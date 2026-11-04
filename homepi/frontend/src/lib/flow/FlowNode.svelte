<script lang="ts">
	import { Handle, Position, useUpdateNodeInternals } from '@xyflow/svelte';
	import Icon from '../Icon.svelte';
	import { live } from '../live.svelte.ts';
	import { pick } from './pick.svelte.ts';
	import { activity } from './activity.svelte.ts';
	import { activeOutputs, CATEGORY_BADGE, CATEGORY_NAME, CATEGORY_STYLE, DEFS, inputs, NODE_ICON, outputs, summary } from './catalog.ts';

	let { id, data, selected, type }: { id: string; data: Record<string, any>; selected?: boolean; type: string } = $props();
	const updateInternals = useUpdateNodeInternals();

	const def = $derived(DEFS[type]);
	const category = $derived(def?.category ?? 'action');
	const text = $derived(summary(type, data, live.devices));
	const outs = $derived(outputs(type, data, live.devices));
	const branching = $derived(outs.length > 1 || outs.some((o) => o.label));
	const ins = $derived(inputs(type, data));
	const active = $derived(activeOutputs(type, id, data, live.devices));
	const left = $derived(id in activity.waiting ? Math.max(0, (activity.waiting[id] - activity.now) / 1000) : undefined);
	const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

	// Outputs change when another device is picked; tell the canvas to re-measure the handles.
	$effect(() => {
		outs.map((o) => o.id).join();
		ins.map((i) => i.id).join();
		updateInternals(id);
	});
</script>

{#snippet next(handle: string)}
	<!-- The + beside an output: add the next step, already connected. -->
	<button class="nodrag nopan btn btn-circle btn-primary absolute top-1/2 -right-11 size-6 min-h-0 -translate-y-1/2 p-0 opacity-70 hover:opacity-100"
		aria-label="Add next step" title="Add next step" onclick={(e) => { e.stopPropagation(); pick.from = { id, handle }; }}>
		<Icon name="plus" class="size-4" />
	</button>
{/snippet}

<div class="bg-base-100 text-base-content relative w-64 rounded-xl border shadow-md"
	class:border-primary={selected} class:ring-2={selected} class:ring-primary={selected}
	style={selected ? '' : left !== undefined ? 'border-color: var(--flow-wait); box-shadow: 0 0 0 2px var(--flow-wait)'
		: 'border-color: color-mix(in oklab, currentColor 15%, transparent)'}>
	<span class="absolute inset-y-0 left-0 w-1.5 rounded-l-xl {CATEGORY_STYLE[category]}"></span>
	<div class="flex items-center gap-2.5 py-2.5 pr-3 pl-4">
		<span class="grid size-9 shrink-0 place-items-center rounded-lg {CATEGORY_BADGE[category]}">
			<Icon name={NODE_ICON[type] ?? 'circle'} class="size-5" />
		</span>
		<div class="min-w-0">
			<div class="text-[11px] font-semibold tracking-wider uppercase opacity-60">{CATEGORY_NAME[category]}</div>
			<div class="text-[15px] leading-tight font-bold">{def?.label ?? type}</div>
		</div>
	</div>
	<div class="bg-base-200 py-2 pr-3 pl-4 text-sm leading-snug break-words {branching || ins.length ? '' : 'rounded-b-xl'}">
		{text}
		{#if left !== undefined}
			<div class="mt-1 font-semibold" style="color: var(--flow-wait)">Counting down · {clock(left)} left</div>
		{/if}
	</div>

	{#if ins.length}
		<!-- One labelled row per input; connect to the dot at the start of a row. -->
		<div class="flex flex-col {branching ? '' : 'rounded-b-xl'}">
			{#each ins as i (i.id)}
				<div class="relative flex items-center gap-2 border-t py-2 pr-4 pl-4 text-sm font-medium"
					style="border-color: color-mix(in oklab, currentColor 10%, transparent)">
					<Handle type="target" position={Position.Left} id={i.id} />
					<span class="bg-base-content/50 size-2 rounded-full"></span>
					{i.label}
				</div>
			{/each}
		</div>
	{/if}

	{#if branching}
		<!-- One labelled row per outcome; drag from the dot at the end of a row. -->
		<div class="flex flex-col rounded-b-xl">
			{#each outs as o, i (o.id)}
				{#if o.group && o.group !== outs[i - 1]?.group}
					<!-- A heading for a group of outputs, e.g. one profile of a remote. -->
					<div class="border-t-2 border-info px-4 pt-2 pb-1 text-left text-[11px] font-bold tracking-wider uppercase">
						<span class="opacity-60">{o.group}</span>
					</div>
				{/if}
				<!-- The output that is true right now is highlighted, like its connection. -->
				<div class="relative flex items-center justify-start gap-2 py-2 pr-4 pl-4 text-sm font-medium {o.group && o.group === outs[i - 1]?.group || !o.group ? 'border-t' : ''}"
					style="border-color: color-mix(in oklab, currentColor 10%, transparent){active.includes(o.id)
						? '; background: color-mix(in oklab, currentColor 10%, transparent); font-weight: 700' : ''}">
					{#if active.includes(o.id)}<span class="text-[11px] font-bold tracking-wide uppercase opacity-70">Now</span>{/if}
					<span class="bg-base-content/50 size-2 rounded-full"></span>
					{o.label}
					<Handle type="source" position={Position.Right} id={o.id} />
					{@render next(o.id)}
				</div>
			{/each}
		</div>
	{:else if outs.length}
		<Handle type="source" position={Position.Right} id={outs[0].id} />
	{@render next(outs[0].id)}
	{/if}
</div>

{#if category !== 'trigger' && !ins.length}
	<Handle type="target" position={Position.Left} />
{/if}
