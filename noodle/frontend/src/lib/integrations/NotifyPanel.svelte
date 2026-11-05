<script lang="ts">
	import { api } from '../api.ts';
	import type { PanelProps } from './types.ts';

	/** How to receive Ntfy notifications on a phone, and a test. */
	let { item }: PanelProps = $props();
	let busy = $state(false);
	let result = $state<{ ok: boolean; text: string } | null>(null);
	let info = $state<{ server: string; topic: string } | null>(null);

	// Asked once when the panel opens; the topic is a secret that the settings form does not send back.
	$effect(() => {
		api<NonNullable<typeof info>>('/notify').then((n) => (info = n)).catch(() => {});
	});

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

{#if item.connected && info?.topic}
	<div class="bg-base-200 rounded-box flex flex-col gap-2 p-3 text-sm">
		<p class="opacity-70">In the <b>ntfy</b> app, tap +, and subscribe to this topic on <code>{info.server}</code>:</p>
		<div class="join">
			<input class="input input-sm join-item grow font-mono" readonly value={info.topic} aria-label="ntfy topic" />
			<button type="button" class="btn btn-sm join-item" onclick={() => navigator.clipboard?.writeText(info!.topic)}>Copy</button>
		</div>
	</div>
{/if}
<div class="flex items-center gap-3">
	<button type="button" class="btn btn-ghost btn-sm" disabled={busy || !item.connected} onclick={test}>Send test</button>
	{#if result}<span class="text-sm {result.ok ? 'text-success' : 'text-error'}">{result.text}</span>{/if}
</div>
