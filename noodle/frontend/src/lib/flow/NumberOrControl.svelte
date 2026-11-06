<script lang="ts">
	import type { CardControl } from '../live.svelte';

	/** A number in a node's settings that is either fixed or comes from a dial or slider on the flow's card.
	 * The card control is stored as "{control.<id>}"; nobody has to type that. */
	let { label, value, controls = [], step = 1, fallback = 0, onchange }: {
		label: string;
		value: unknown;
		controls?: CardControl[];
		step?: number;
		/** The number to go back to when the card control is let go. */
		fallback?: number;
		onchange: (value: number | string) => void;
	} = $props();

	const usable = $derived(controls.filter((c) => c.type === 'dial' || c.type === 'slider'));
	const bound = $derived(typeof value === 'string' ? (value.match(/^\{control\.([a-z][a-z0-9_]*)\}$/)?.[1] ?? null) : null);
	const boundControl = $derived(usable.find((c) => c.id === bound));
</script>

<div class="flex grow items-end gap-2">
	{#if bound === null}
		<label class="floating-label grow"><span>{label}</span>
			<input type="number" {step} class="input input-sm w-full" value={value as number} onchange={(e) => onchange(Number(e.currentTarget.value))} /></label>
	{:else}
		<div class="grow text-sm"><span class="opacity-60">{label}:</span> from <b>{boundControl?.label ?? bound}</b> on the card</div>
	{/if}
	{#if usable.length || bound !== null}
		<select class="select select-sm w-40" aria-label="{label}: where the number comes from" value={bound ?? ''}
			onchange={(e) => onchange(e.currentTarget.value ? `{control.${e.currentTarget.value}}` : fallback)}>
			<option value="">A fixed number</option>
			{#each usable as c (c.id)}<option value={c.id}>From {c.label ?? c.id}</option>{/each}
			{#if bound !== null && !boundControl}<option value={bound}>A control that is gone</option>{/if}
		</select>
	{/if}
</div>
