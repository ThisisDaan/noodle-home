<script lang="ts">
	import Icon from './Icon.svelte';
	import { api } from './api';
	import { groupEditor } from './groups.svelte';
	import { live } from './live.svelte';

	let dialog: HTMLDialogElement;
	let error = $state('');
	let busy = $state(false);

	const g = $derived(groupEditor.editing);
	// Every lamp that can be in a group (not other groups), sorted by room so they are easy to find.
	const lamps = $derived(
		live.list
			.filter((d) => d.source !== 'group')
			.flatMap((d) => d.entities.filter((e) => e.kind === 'light').map((e) => ({ d, e, id: `${d.id}|${e.key}` })))
			.sort((a, b) => (a.d.area ?? '~').localeCompare(b.d.area ?? '~') || a.d.name.localeCompare(b.d.name))
	);

	$effect(() => {
		if (g && !dialog.open) {
			error = '';
			dialog.showModal();
		}
		if (!g && dialog?.open) dialog.close();
	});

	function pick(id: string, on: boolean) {
		if (!g) return;
		g.members = on ? [...g.members, id] : g.members.filter((m) => m !== id);
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		if (!g) return;
		error = '';
		busy = true;
		try {
			const body = { name: g.name.trim(), members: g.members.map((m) => ({ device_id: m.split('|')[0], key: m.split('|')[1] })) };
			await api(g.id ? `/groups/${g.id}` : '/groups', { method: g.id ? 'PUT' : 'POST', body });
			groupEditor.close();
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}

	async function remove() {
		if (!g?.id || !confirm(`Delete group "${g.name}"? The lamps themselves stay.`)) return;
		await api(`/groups/${g.id}`, { method: 'DELETE' });
		groupEditor.close();
	}
</script>

<dialog class="modal modal-bottom sm:modal-middle" bind:this={dialog} onclose={() => groupEditor.close()}>
	<div class="modal-box flex flex-col gap-4 overflow-hidden">
		{#if g}
			<div class="flex shrink-0 items-center gap-3">
				<span class="icon-bubble"><Icon name="bulb" /></span>
				<h2 class="grow text-lg font-bold">{g.id ? 'Edit light group' : 'New light group'}</h2>
				<form method="dialog"><button class="btn btn-ghost btn-sm btn-circle" aria-label="Close"><Icon name="close" /></button></form>
			</div>
			<div class="flex min-h-0 flex-col gap-4 overflow-y-auto">
			<p class="text-sm opacity-70">
				The lamps you tick act as one light: one switch and one brightness slider on the dashboard, and one device in
				your flows. The lamps also still work on their own.
			</p>
			<form class="flex flex-col gap-4" onsubmit={save}>
				<label class="floating-label">
					<span>Name</span>
					<input class="input w-full" bind:value={g.name} placeholder="Name, e.g. Woonkamer lampen" required maxlength="60" />
				</label>
				<fieldset class="fieldset">
					<legend class="fieldset-legend">Lamps in this group ({g.members.length})</legend>
					<div class="bg-base-200 rounded-box flex max-h-72 flex-col gap-1 overflow-y-auto p-2">
						{#each lamps as l (l.id)}
							<label class="hover:bg-base-300 rounded-field flex cursor-pointer items-center gap-3 p-2">
								<input type="checkbox" class="checkbox checkbox-sm" checked={g.members.includes(l.id)}
									onchange={(e) => pick(l.id, e.currentTarget.checked)} />
								<span class="grow">{l.d.name}{l.d.entities.filter((e) => e.kind === 'light').length > 1 ? ` · ${l.e.name}` : ''}</span>
								<span class="text-xs opacity-60">{l.d.area ?? 'No room'}</span>
							</label>
						{:else}
							<p class="p-2 text-sm opacity-60">No lamps found.</p>
						{/each}
					</div>
				</fieldset>
				{#if error}<div role="alert" class="alert alert-error alert-soft text-sm">{error}</div>{/if}
				<div class="flex gap-2">
					{#if g.id}<button type="button" class="btn btn-error btn-outline" onclick={remove}>Delete group</button>{/if}
					<button class="btn btn-primary ml-auto" disabled={busy || !g.name.trim() || !g.members.length}>
						{g.id ? 'Save group' : 'Create group'}
					</button>
				</div>
			</form>
			</div>
		{/if}
	</div>
	<form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>
