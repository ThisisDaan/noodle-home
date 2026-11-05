<script lang="ts">
	import { api } from '../api.ts';
	import Discover from './Discover.svelte';
	import { PANELS } from './panels.ts';
	import type { Integration } from './types.ts';

	let { item, onchange, onremove, removable = true, formId, hideActions = false, onsaved }: {
		item: Integration;
		/** The integration's new state after saving, adding or removing. */
		onchange: (updated: Integration) => void;
		onremove?: () => void;
		removable?: boolean;
		/** Set-up dialog: the dialog has the buttons (a submit button with form={formId}); `onsaved` runs after a save that connected. */
		formId?: string;
		hideActions?: boolean;
		onsaved?: (saved: Integration) => void;
	} = $props();

	const Panel = $derived(item.panel ? PANELS[item.panel] : undefined);

	let values = $state<Record<string, string>>({});
	let busy = $state(false);
	let message = $state<{ ok: boolean; text: string } | null>(null);

	// What the fields hold follows the integration (it changes after a save or a panel's action).
	$effect(() => {
		values = Object.fromEntries(item.fields.map((f) => [f.key, f.value]));
	});

	async function save() {
		busy = true;
		message = null;
		try {
			const saved = await api<Integration>(`/integrations/${item.id}`, { method: 'PUT', body: { values: Object.fromEntries(Object.entries(values).filter(([key]) => !item.fields.find((f) => f.key === key)?.hidden)) } });
			onchange(saved);
			// The server restarts the connection (if there is one) before it answers, so this is the result.
			message = saved.connected === false
				? { ok: false, text: 'Saved, but not connected. Check the values.' }
				: { ok: true, text: saved.connected ? 'Saved and connected.' : 'Saved.' };
			if (saved.connected !== false) onsaved?.(saved);
		} catch (err) {
			message = { ok: false, text: err instanceof Error ? err.message : String(err) };
		} finally {
			busy = false;
		}
	}

	async function remove() {
		if (!confirm(`Remove ${item.name}? Its devices disappear from this hub. Nothing is deleted on the service itself.`)) return;
		onchange(await api<Integration>(`/integrations/${item.id}`, { method: 'DELETE' }));
		onremove?.();
	}
</script>

<form id={formId} class="flex flex-col gap-3" onsubmit={(e) => { e.preventDefault(); save(); }}>
	{#if !item.custom_form}<p class="text-sm opacity-70">{item.help}</p>{/if}

	{#each item.custom_form ? [] : item.fields.filter((f) => !f.hidden && !f.advanced) as f (f.key)}
		<label class="floating-label">
			<span>{f.label}{f.secret && f.set ? ' (saved, leave empty to keep)' : ''}</span>
			<input class="input w-full" bind:value={values[f.key]} placeholder={f.label} autocomplete="off"
				type={f.secret ? 'password' : 'text'} />
		</label>
		{#if f.help}<p class="-mt-2 text-xs opacity-60">{f.help}</p>{:else if f.placeholder && !f.secret}<p class="-mt-2 text-xs opacity-50">Example: {f.placeholder}</p>{/if}
	{/each}

	{#if item.searchable}<Discover {item} {onchange} />{/if}
	{#if Panel}<Panel {item} {onchange} />{/if}
	{#if !item.custom_form && item.fields.some((f) => f.advanced)}
		<details class="bg-base-200 rounded-box p-3">
			<summary class="cursor-pointer text-sm font-medium">Advanced</summary>
			<div class="mt-3 flex flex-col gap-3">
				{#each item.fields.filter((f) => f.advanced && !f.hidden) as f (f.key)}
					<label class="floating-label">
						<span>{f.label}</span>
						<input class="input w-full" bind:value={values[f.key]} placeholder={f.label} autocomplete="off" type="text" />
					</label>
					{#if f.help}<p class="-mt-2 text-xs opacity-60">{f.help}</p>{/if}
				{/each}
			</div>
		</details>
	{/if}

	{#if message}
		<div role="alert" class="alert alert-soft text-sm {message.ok ? 'alert-success' : 'alert-error'}">{message.text}</div>
	{/if}

	<div class="flex flex-wrap items-center justify-end gap-2" class:hidden={hideActions}>
		{#if removable && !item.always}
			<button type="button" class="btn btn-ghost btn-sm text-error mr-auto" onclick={remove}>Remove</button>
		{/if}
		{#if item.fields.length && !item.custom_form}
			<button class="btn btn-primary btn-sm" disabled={busy}>
				{#if busy}<span class="loading loading-spinner loading-xs"></span>{/if}Save
			</button>
		{/if}
	</div>
</form>
