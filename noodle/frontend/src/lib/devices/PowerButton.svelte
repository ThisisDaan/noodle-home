<script lang="ts">
	import Icon from '../Icon.svelte';

	/** The one on/off button for every light, plug and switch. */
	let { on, label, disabled = false, fill = '', fillCss = '', onclick }: {
		/** a hex colour as a style */
		fillCss?: string;
		on: boolean;
		/** the colour it takes when on (a class), else the usual amber */
		fill?: string;
		disabled?: boolean;
		label: string;
		onclick: () => void;
	} = $props();

	// One look for every on/off, whatever the device. A little see-through while on, so it is not as solid as the full colour.
	const onLook = 'border-transparent bg-warning/75 text-warning-content hover:bg-warning/85';
</script>

<!-- 3rem, but never wider than its place on the card: on a phone the card's columns are narrow, and a fixed size ran into the next component. -->
<button type="button" class="btn btn-circle aspect-square min-h-0 min-w-0 shrink-0 p-0 {on ? (fill || fillCss ? `border-transparent ${fill} text-base-content` : onLook) : 'btn-soft'}" aria-pressed={on} {disabled} style="width: min(3rem, 100%); height: auto;{on && fillCss ? ` ${fillCss}` : ''}"
	aria-label="Turn {label} {on ? 'off' : 'on'}" {onclick}>
	<Icon name="power" class="size-5" />
</button>
