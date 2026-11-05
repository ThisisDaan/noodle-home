<script lang="ts">
	import Icon from './Icon.svelte';
	import DeviceFace from './devices/DeviceFace.svelte';
	import TileSubtitle from './devices/TileSubtitle.svelte';
	import { motionActive } from './devices/kinds.ts';
	import { iconFor, isOn, type Device } from './api';
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

	let dragging = $state(false);
	let over = $state(false);
	const lit = $derived(isOn(device) || motionActive(device));
</script>

<!-- Every card has the same structure and height: the name with one line under it, and a bottom row (DeviceFace)
     that is always 3rem high. Battery and other properties are in the device's sheet, not here. -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="tile group relative flex flex-col justify-between gap-3 p-3.5"
	class:h-36={!editing}
	class:is-on={lit}
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
				<span class="block truncate text-xs opacity-60"><TileSubtitle {device} /></span>
			</span>
		</button>
		{#if editing}
			<span class="opacity-50" title="Drag to reorder"><Icon name="grip" /></span>
		{:else if layout.isFavorite(device.id)}
			<Icon name="star" class="text-accent size-4 shrink-0 fill-current" />
		{/if}
	</div>

	{#if !editing}<div class="relative z-10"><DeviceFace {device} size="tile" /></div>{/if}

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
