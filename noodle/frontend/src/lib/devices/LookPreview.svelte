<script lang="ts">
	/** A tiny picture of how a component looks, for the designer's pickers. `look` is a style or a component name. */
	let { look, class: cls = '' }: { look: string; class?: string } = $props();
</script>

<svg viewBox="0 0 48 28" class="{cls} text-base-content" fill="none" role="img" aria-hidden="true">
	{#if look === 'text-l'}
		<text x="24" y="21" text-anchor="middle" font-size="19" font-weight="800" fill="currentColor">21°</text>
	{:else if look === 'text-m'}
		<text x="24" y="19" text-anchor="middle" font-size="12" font-weight="700" fill="currentColor">Text</text>
	{:else if look === 'text-s'}
		<text x="24" y="17" text-anchor="middle" font-size="8" font-weight="600" fill="currentColor">Small</text>
	{:else if look === 'label'}
		<rect x="6" y="8" width="30" height="4" rx="2" fill="currentColor" opacity="0.8" /><rect x="6" y="16" width="20" height="4" rx="2" fill="currentColor" opacity="0.4" />
	{:else if look === 'chip'}
		<rect x="3" y="6" width="42" height="16" rx="5" class="fill-warning/30" /><rect x="9" y="12.5" width="22" height="3" rx="1.5" class="fill-warning" />
	{:else if look === 'icon'}
		<circle cx="24" cy="14" r="9" fill="currentColor" opacity="0.2" /><circle cx="24" cy="14" r="4" fill="currentColor" />
	{:else if look === 'gauge'}
		<path d="M10 22 A14 14 0 1 1 38 22" stroke="currentColor" stroke-width="4" stroke-linecap="round" opacity="0.2" />
		<path d="M10 22 A14 14 0 0 1 30 9" class="stroke-primary" stroke-width="4" stroke-linecap="round" />
	{:else if look === 'bar'}
		<rect x="3" y="10" width="42" height="8" rx="4" fill="currentColor" opacity="0.2" /><rect x="3" y="10" width="26" height="8" rx="4" class="fill-primary" />
	{:else if look === 'line'}
		<path d="M3 22 L12 14 L20 18 L30 7 L45 12 L45 26 L3 26Z" class="fill-primary/15" /><path d="M3 22 L12 14 L20 18 L30 7 L45 12" class="stroke-primary" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
	{:else if look === 'bars'}
		{#each [10, 16, 12, 20, 15, 22, 18] as h, i (i)}<rect x={4 + i * 6} y={26 - h} width="4" height={h} rx="1" class="fill-primary" opacity="0.75" />{/each}
	{:else if look === 'spark'}
		<text x="3" y="17" font-size="9" font-weight="700" fill="currentColor">21</text><path d="M20 20 L26 12 L32 16 L38 8 L45 12" class="stroke-primary" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
	{:else if look === 'switch'}
		<rect x="9" y="7" width="30" height="14" rx="7" class="fill-primary/30" /><circle cx="32" cy="14" r="5" class="fill-primary" />
	{:else if look === 'slider'}
		<rect x="4" y="12" width="40" height="4" rx="2" fill="currentColor" opacity="0.2" /><rect x="4" y="12" width="24" height="4" rx="2" class="fill-primary" /><circle cx="28" cy="14" r="5" class="fill-primary" />
	{:else if look === 'dial'}
		<circle cx="24" cy="14" r="10" stroke="currentColor" stroke-width="3" opacity="0.2" /><path d="M24 4 A10 10 0 0 1 34 14" class="stroke-primary" stroke-width="3" stroke-linecap="round" /><text x="24" y="17" text-anchor="middle" font-size="8" font-weight="700" fill="currentColor">21</text>
	{/if}
</svg>
