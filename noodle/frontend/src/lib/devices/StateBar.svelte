<script lang="ts">
	/** The bar next to the power button for something that only switches on and off. It looks like the brightness
	 * bar of a dimmable light (LevelBar), full while on, and pressing it switches too. */
	let { on, label, text, disabled = false, onclick }: {
		on: boolean;
		label: string;
		text: string;
		disabled?: boolean;
		onclick: () => void;
	} = $props();
</script>

<button type="button" class="bg-base-content/10 rounded-box relative h-12 grow overflow-hidden active:brightness-90" aria-pressed={on}
	aria-label="Turn {label} {on ? 'off' : 'on'}" {disabled} {onclick}>
	<span class="bg-warning/50 absolute inset-0 transition-opacity" class:opacity-0={!on}></span>
	<span class="absolute inset-0 grid place-items-center font-bold tabular-nums">{text}</span>
</button>
