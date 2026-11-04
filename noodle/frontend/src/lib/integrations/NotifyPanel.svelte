<script lang="ts">
	import { api } from '../api.ts';
	import type { PanelProps } from './types.ts';

	let { item }: PanelProps = $props();
	let busy = $state(false);
	let result = $state<{ ok: boolean; text: string } | null>(null);

	async function test() {
		busy = true;
		result = null;
		try {
			await api('/notify/test', { body: {} });
			result = { ok: true, text: 'Test sent. Check your phone.' };
		} catch (err) {
			result = { ok: false, text: err instanceof Error ? err.message : String(err) };
		} finally {
			busy = false;
		}
	}
</script>

<div class="flex items-center gap-3">
	<button type="button" class="btn btn-ghost btn-sm" disabled={busy || !item.connected} onclick={test}>Send test</button>
	{#if result}<span class="text-sm {result.ok ? 'text-success' : 'text-error'}">{result.text}</span>{/if}
</div>
