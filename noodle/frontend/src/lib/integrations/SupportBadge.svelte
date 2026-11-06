<script lang="ts">
	import type { Integration } from './types.ts';

	/** Whether the maintainers have run this integration on real devices (backend Plugin.support). */
	let { support }: { support: Integration['support'] } = $props();
</script>

{#if support === 'supported'}
	<span class="badge badge-success badge-soft badge-sm" title="Used on real devices by the maintainers">Supported</span>
{:else}
	<span class="badge badge-warning badge-soft badge-sm" title="Written from the device's protocol but not yet confirmed on real hardware. It may need fixes: please report what you see.">Untested</span>
{/if}
