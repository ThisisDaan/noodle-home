<script lang="ts">
	import Icon from './Icon.svelte';
	import { api } from './api';
	import { combineEditor, type Template, type TemplateInput } from './combine.svelte';
	import { live } from './live.svelte';

	let dialog: HTMLDialogElement;
	let error = $state('');
	let busy = $state(false);
	let templates = $state<Template[]>([]);

	const c = $derived(combineEditor.editing);
	const template = $derived(templates.find((t) => t.id === c?.template));
	const deviceInputs = $derived(template?.inputs.filter((i) => i.kind !== 'number') ?? []);
	const numberInputs = $derived(template?.inputs.filter((i) => i.kind === 'number') ?? []);

	// What can be picked for a sensor or a switch input, sorted by room so it is easy to find.
	function choices(input: TemplateInput) {
		const wanted = (e: { kind: string; device_class?: string | null }) =>
			input.kind === 'switch' ? e.kind === 'switch' : e.kind === 'sensor' && (!input.device_class || e.device_class === input.device_class);
		return live.list
			.filter((d) => d.source !== 'combined')
			.flatMap((d) => d.entities.filter(wanted).map((e) => ({ d, e, id: `${d.id}|${e.key}` })))
			.sort((a, b) => (a.d.area ?? '~').localeCompare(b.d.area ?? '~') || a.d.name.localeCompare(b.d.name));
	}

	$effect(() => {
		if (c && !dialog.open) {
			error = '';
			dialog.showModal();
			if (!templates.length) api<Template[]>('/combined/templates').then((t) => (templates = t)).catch(() => {});
		}
		if (!c && dialog?.open) dialog.close();
	});

	// Fill the defaults of a new device once the template is known.
	$effect(() => {
		if (c && template) {
			for (const i of template.inputs) if (c.values[i.key] === undefined && i.default !== null) c.values[i.key] = i.default;
		}
	});

	const picked = (key: string) => (c?.values[`${key}_device`] ? `${c.values[`${key}_device`]}|${c.values[`${key}_key`]}` : '');
	function pick(key: string, value: string) {
		if (!c) return;
		const [device, k] = value.split('|');
		c.values[`${key}_device`] = device ?? '';
		c.values[`${key}_key`] = k ?? '';
	}
	function chooseTemplate(id: string) {
		if (c) {
			c.template = id;
			c.values = {};
		}
	}
	const ready = $derived(!!c?.name.trim() && deviceInputs.every((i) => !!c?.values[`${i.key}_device`]));

	async function save(e: SubmitEvent) {
		e.preventDefault();
		if (!c) return;
		error = '';
		busy = true;
		try {
			const body = { template: c.template, name: c.name.trim(), values: c.values };
			await api(c.id ? `/combined/${c.id}` : '/combined', { method: c.id ? 'PUT' : 'POST', body });
			combineEditor.close();
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}

	async function remove() {
		if (!c?.id || !confirm(`Delete "${c.name}"? The devices it is made from stay.`)) return;
		await api(`/combined/${c.id}`, { method: 'DELETE' });
		combineEditor.close();
	}
</script>

<dialog class="modal modal-bottom sm:modal-middle" bind:this={dialog} onclose={() => combineEditor.close()}>
	<div class="modal-box flex flex-col gap-4 overflow-hidden">
		{#if c}
			<div class="flex shrink-0 items-center gap-3">
				<span class="icon-bubble"><Icon name="thermo" /></span>
				<h2 class="grow text-lg font-bold">{c.id ? 'Edit combined device' : 'Combine devices'}</h2>
				<form method="dialog"><button class="btn btn-ghost btn-sm btn-circle" aria-label="Close"><Icon name="close" /></button></form>
			</div>
			<div class="flex min-h-0 flex-col gap-4 overflow-y-auto">
				{#if template}
					{#if !c.id && templates.length > 1}
						<label class="floating-label">
							<span>Make</span>
							<select class="select w-full" value={c.template} onchange={(e) => chooseTemplate(e.currentTarget.value)}>
								{#each templates as t (t.id)}<option value={t.id}>{t.name}</option>{/each}
							</select>
						</label>
					{/if}
					<p class="text-sm opacity-70">{template.help}</p>
					<p class="text-xs opacity-60">
						This makes one device in your list. Where something has to be done, a normal automation called
						"{c.name || template.name} (combined)" does it. You can open and read it.
					</p>
					<form class="flex flex-col gap-4" onsubmit={save}>
						<label class="floating-label">
							<span>Name</span>
							<input class="input w-full" bind:value={c.name} placeholder="Name, e.g. Study {template.name.toLowerCase()}" required maxlength="60" />
						</label>
						{#each deviceInputs as i (i.key)}
							<label class="floating-label">
								<span>{i.label}</span>
								<select class="select w-full" required value={picked(i.key)} onchange={(e) => pick(i.key, e.currentTarget.value)}>
									<option value="" disabled>Choose...</option>
									{#each choices(i) as o (o.id)}
										<option value={o.id}>{o.d.name}{o.d.area ? ` · ${o.d.area}` : ''}</option>
									{/each}
								</select>
							</label>
						{/each}
						{#each numberInputs as i (i.key)}
							<label class="floating-label">
								<span>{i.label}</span>
								<input type="number" step="any" class="input w-full" bind:value={c.values[i.key]} required />
							</label>
						{/each}
						{#if error}<div role="alert" class="alert alert-error alert-soft text-sm">{error}</div>{/if}
						<div class="flex gap-2">
							{#if c.id}<button type="button" class="btn btn-error btn-outline" onclick={remove}>Delete</button>{/if}
							<button class="btn btn-primary ml-auto" disabled={busy || !ready}>{c.id ? 'Save' : 'Create'}</button>
						</div>
					</form>
				{:else}
					<p class="text-sm opacity-60">Loading...</p>
				{/if}
			</div>
		{/if}
	</div>
	<form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>
