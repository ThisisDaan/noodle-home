<script lang="ts">
	import { api } from '../api.ts';
	import type { PanelProps } from './types.ts';

	/** What Zigbee2MQTT says about itself, and a link to its own pages. Pairing devices is the Search above. */
	let { item }: PanelProps = $props();
	let info = $state<{ connected: boolean; online: boolean; version: string | null } | null>(null);

	// Asked once when the panel opens (the hub does not push this).
	$effect(() => {
		api<{ zigbee?: typeof info }>('/system').then((s) => (info = s.zigbee ?? null)).catch(() => {});
	});
	const url = $derived(item.fields.find((f) => f.key === 'z2m_url')?.value || `${location.protocol}//${location.hostname}:8081`);
</script>

<div class="bg-base-200 rounded-box flex flex-wrap items-center gap-3 p-3">
	<span class="status {info?.connected && info.online ? 'status-success' : info ? 'status-error' : 'status-neutral'}"></span>
	<span class="grow text-sm">
		{#if !info}Checking…
		{:else if !info.connected}Cannot reach the MQTT broker
		{:else if !info.online}Zigbee2MQTT is offline
		{:else}Zigbee2MQTT {info.version ?? ''} is running{/if}
	</span>
	<a class="btn btn-sm btn-outline" href={url} target="_blank" rel="noopener">Open Zigbee2MQTT</a>
</div>
