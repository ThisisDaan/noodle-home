<script lang="ts">
	import Icon from './Icon.svelte';
	import { command, headline, iconFor, isOn, type Device } from './api';
	import { layout, ui } from './layout.svelte';

	type Props = {
		device: Device;
		editing?: boolean;
		first?: boolean;
		last?: boolean;
		onnudge?: (delta: number) => void;
		ondragstart?: () => void;
		ondrop?: () => void;
	};
	let { device, editing = false, first = false, last = false, onnudge, ondragstart, ondrop }: Props = $props();

	let busy = $state(false);
	let dragging = $state(false);
	let over = $state(false);

	const on = $derived(isOn(device));
	// The one entity a quick tap should flip: the first light, else the first switch.
	const primary = $derived(
		device.entities.find((e) => e.kind === 'light') ?? device.entities.find((e) => e.kind === 'switch')
	);
	const level = $derived(device.entities.find((e) => e.kind === 'light' && e.brightness !== null));

	async function flip(e: Event) {
		e.stopPropagation();
		if (!primary || busy) return;
		busy = true;
		try {
			await command(device, primary, { toggle: true });
		} finally {
			busy = false;
		}
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="tile group flex min-h-28 flex-col gap-2 p-3.5"
	class:is-on={on}
	class:is-dragging={dragging}
	class:is-over={over}
	class:opacity-60={!device.available && !editing}
	class:cursor-grab={editing}
	draggable={editing}
	ondragstart={(e) => {
		dragging = true;
		e.dataTransfer?.setData('text/plain', device.id);
		ondragstart?.();
	}}
	ondragend={() => (dragging = false)}
	ondragover={(e) => {
		if (!editing) return;
		e.preventDefault();
		over = true;
	}}
	ondragleave={() => (over = false)}
	ondrop={(e) => {
		e.preventDefault();
		over = false;
		ondrop?.();
	}}
>
	<div class="flex items-start gap-3">
		<button
			class="tile-main flex min-w-0 grow items-start gap-3 rounded-lg text-left after:absolute after:inset-0 after:rounded-[inherit] after:content-['']"
			onclick={() => ui.open(device.id)}
			aria-label="Open {device.name}"
		>
			<span class="icon-bubble"><Icon name={iconFor(device)} /></span>
			<span class="min-w-0">
				<span class="block truncate leading-tight font-semibold">{device.name}</span>
				<span class="block truncate text-sm opacity-70">{headline(device)}</span>
			</span>
		</button>

		{#if editing}
			<span class="opacity-50" title="Drag to reorder"><Icon name="grip" /></span>
		{:else if primary && device.available}
			<input
				type="checkbox"
				class="toggle toggle-primary relative z-10 shrink-0"
				checked={on}
				disabled={busy}
				aria-label="Toggle {device.name}"
				onclick={flip}
			/>
		{/if}
	</div>

	<div class="mt-auto flex items-center gap-2 text-xs opacity-70">
		{#if level && on}
			<progress class="progress progress-accent h-1.5 grow" value={level.brightness} max="100"></progress>
		{:else}
			<span class="grow"></span>
		{/if}
		{#if !device.available}<span class="badge badge-error badge-soft badge-xs">offline</span>{/if}
		{#if device.battery !== null}
			<span class="flex items-center gap-1" class:text-warning={device.battery < 20}>
				<Icon name="battery" class="size-4" />{device.battery}%
			</span>
		{/if}
		{#if layout.isFavorite(device.id) && !editing}<Icon name="star" class="text-accent size-4 fill-current" />{/if}
	</div>

	{#if editing}
		<div class="border-base-content/10 relative z-10 flex items-center gap-1 border-t pt-2">
			<button class="btn btn-ghost btn-xs btn-square" aria-label="Move earlier" disabled={first} onclick={() => onnudge?.(-1)}>
				<Icon name="left" class="size-4" />
			</button>
			<button class="btn btn-ghost btn-xs btn-square" aria-label="Move later" disabled={last} onclick={() => onnudge?.(1)}>
				<Icon name="right" class="size-4" />
			</button>
			<span class="grow"></span>
			<button
				class="btn btn-ghost btn-xs btn-square"
				class:text-accent={layout.isFavorite(device.id)}
				aria-label="Pin to favourites"
				onclick={() => layout.toggleFavorite(device.id)}
			>
				<Icon name="star" class="size-4 {layout.isFavorite(device.id) ? 'fill-current' : ''}" />
			</button>
			<button class="btn btn-ghost btn-xs" onclick={() => layout.toggleHidden(device.id)}>
				<Icon name="eyeoff" class="size-4" />Hide
			</button>
		</div>
	{/if}
</div>
