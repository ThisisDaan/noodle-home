<script lang="ts">
	import Icon from './Icon.svelte';
	import { api } from './api';
	import { customEditor, type CustomField } from './custom.svelte';

	let dialog: HTMLDialogElement;
	let error = $state('');
	let busy = $state(false);

	const c = $derived(customEditor.editing);
	const TYPES: [CustomField['type'], string][] = [['switch', 'On / off'], ['number', 'Number'], ['text', 'Text']];

	$effect(() => {
		if (c && !dialog.open) {
			error = '';
			dialog.showModal();
		}
		if (!c && dialog?.open) dialog.close();
	});

	function addField() {
		c?.fields.push({ label: '', type: 'text' });
	}
	function removeField(field: CustomField) {
		if (c) c.fields.splice(c.fields.indexOf(field), 1);
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		if (!c) return;
		error = '';
		busy = true;
		try {
			const body = { name: c.name.trim(), fields: c.fields.filter((f) => f.label.trim()).map((f) => ({ ...f, label: f.label.trim(), unit: f.type === 'number' ? f.unit : undefined })) };
			await api(c.id ? `/custom/${c.id}` : '/custom', { method: c.id ? 'PUT' : 'POST', body });
			customEditor.close();
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}

	async function remove() {
		if (!c?.id || !confirm(`Delete "${c.name}"? Its values are lost. Flows that write to it will report an error.`)) return;
		try {
			await api(`/custom/${c.id}`, { method: 'DELETE' });
			customEditor.close();
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}
</script>

<dialog class="modal modal-bottom sm:modal-middle" bind:this={dialog} onclose={() => customEditor.close()}>
	<div class="modal-box flex flex-col gap-4 overflow-hidden">
		{#if c}
			<div class="flex shrink-0 items-center gap-3">
				<span class="icon-bubble"><Icon name="variable" /></span>
				<h2 class="grow text-lg font-bold">{c.id ? 'Edit custom device' : 'New custom device'}</h2>
				<form method="dialog"><button class="btn btn-ghost btn-sm btn-circle" aria-label="Close"><Icon name="close" /></button></form>
			</div>
			<div class="flex min-h-0 flex-col gap-4 overflow-y-auto">
				<p class="text-sm opacity-70">
					A device you make yourself. Give it the things it should remember (a status, a target, an on/off), and your
					automations fill them in with <b>Write to entity</b>. It then works like any other device: you see it on the Devices
					page and other automations can react to it.
				</p>
				<form class="flex flex-col gap-4" onsubmit={save}>
					<label class="floating-label">
						<span>Name</span>
						<input class="input w-full" bind:value={c.name} placeholder="Name, e.g. Study heater" required maxlength="60" />
					</label>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">What it remembers</legend>
						<div class="flex flex-col gap-2">
							{#each c.fields as f, i (f.key ?? i)}
								<div class="bg-base-200 rounded-box flex flex-wrap items-center gap-2 p-2">
									<input class="input input-sm min-w-0 grow" bind:value={f.label} placeholder="Name, e.g. Status" maxlength="40" aria-label="Field name" />
									<select class="select select-sm w-32" bind:value={f.type} aria-label="Type">
										{#each TYPES as [t, name] (t)}<option value={t}>{name}</option>{/each}
									</select>
									{#if f.type === 'number'}
										<input class="input input-sm w-20" bind:value={f.unit} placeholder="Unit" maxlength="10" aria-label="Unit" />
									{/if}
									<button type="button" class="btn btn-ghost btn-xs btn-square text-error" aria-label="Remove field" onclick={() => removeField(f)}><Icon name="close" class="size-4" /></button>
								</div>
							{/each}
						</div>
						<button type="button" class="btn btn-sm btn-soft mt-2 self-start" onclick={addField}><Icon name="plus" class="size-4" />Add</button>
					</fieldset>
					{#if error}<div role="alert" class="alert alert-error alert-soft text-sm">{error}</div>{/if}
					<div class="flex gap-2">
						{#if c.id && !c.builtin}<button type="button" class="btn btn-error btn-outline" onclick={remove}>Delete</button>{/if}
						<button class="btn btn-primary ml-auto" disabled={busy || !c.name.trim()}>{c.id ? 'Save' : 'Create'}</button>
					</div>
				</form>
			</div>
		{/if}
	</div>
	<form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>
