<script lang="ts">
	import Icon from '../Icon.svelte';

	/** The one on/off button for every light, plug and switch. */
	let { on, label, disabled = false, onclick }: {
		on: boolean;
		disabled?: boolean;
		label: string;
		onclick: () => void;
	} = $props();

	// One look for every on/off, whatever the device. A little see-through while on, so it is not as solid as the full colour.
	const onLook = 'border-transparent bg-warning/75 text-warning-content hover:bg-warning/85';
</script>

<button type="button" class="btn btn-circle size-12 shrink-0 {on ? onLook : 'btn-soft'}" aria-pressed={on} {disabled}
	aria-label="Turn {label} {on ? 'off' : 'on'}" {onclick}>
	<Icon name="power" class="size-5" />
</button>
