<script lang="ts">
	import { goto } from '$app/navigation';
	import ConnectAi from '#lib/ConnectAi.svelte';
	import Icon from '#lib/Icon.svelte';
	import { ago, api } from '#lib/api.ts';
	import { live, type FlowSummary } from '#lib/live.svelte.ts';
	import { TEMPLATES, candidates, type Chosen, type Template } from '#lib/flow/templates.ts';

	// Loaded once; after that the server pushes every change (runs, errors, switching on/off).
	const flows = $derived(live.flows ? [...live.flows].sort((a, b) => a.name.localeCompare(b.name)) : null);
	let error = $state('');

	async function load() {
		try {
			live.flows = await api<FlowSummary[]>('/flows');
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}

	async function blankFlow() {
		const flow = await api<{ id: string }>('/flows', { body: { name: 'New flow' } });
		templateDialog?.close();
		goto(`/automations/flow/${flow.id}`);
	}

	async function setEnabled(f: FlowSummary, enabled: boolean) {
		await api(`/flows/${f.id}`, { method: 'PUT', body: { enabled } });
	}

	async function run(f: FlowSummary) {
		try {
			await api(`/flows/${f.id}/run`, { body: {} });
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}

	// --- templates: pick a recipe, choose the devices, get a ready flow
	let template = $state<Template | null>(null);
	let chosen = $state<Record<string, string>>({}); // pick id -> device id
	let templateDialog = $state<HTMLDialogElement>();

	const options = (t: Template) => t.picks.map((p) => ({ pick: p, list: candidates(p, live.list) }));
	const ready = $derived(!!template && template.picks.every((p) => chosen[p.id]));

	function openNew() {
		template = null;
		templateDialog?.showModal();
	}

	function startTemplate(t: Template) {
		template = t;
		chosen = Object.fromEntries(options(t).map(({ pick, list }) => [pick.id, list.length === 1 ? list[0].device.id : '']));
	}

	async function useTemplate() {
		if (!template) return;
		const picks: Record<string, Chosen> = {};
		for (const { pick, list } of options(template)) {
			const c = list.find((x) => x.device.id === chosen[pick.id]);
			if (c) picks[pick.id] = c;
		}
		const { name, graph } = template.build(picks);
		const flow = await api<{ id: string }>('/flows', { body: { name, graph } });
		templateDialog?.close();
		goto(`/automations/flow/${flow.id}`);
	}

	let aiDialog = $state<HTMLDialogElement>();

	$effect(() => {
		load();
	});
</script>

<div class="mb-6 flex flex-wrap items-end justify-between gap-3">
	<div>
		<h1 class="text-3xl font-bold tracking-tight">Automations</h1>
		<p class="opacity-70">
			{#if flows}{flows.filter((f) => f.enabled).length} of {flows.length} running{:else}Loading…{/if}
		</p>
	</div>
	<div class="flex gap-2">
		<button class="btn btn-sm" onclick={() => aiDialog?.showModal()}><Icon name="note" class="size-4" />Connect an AI</button>
		<button class="btn btn-primary btn-sm" onclick={openNew}><Icon name="plus" class="size-4" />New flow</button>
	</div>
</div>
{#if error}<div role="alert" class="alert alert-error alert-soft mb-4">{error}</div>{/if}
{#each Object.entries(live.flowIssues) as [file, issue] (file)}
	{#if issue.errors.length}
		<div role="alert" class="alert alert-warning alert-soft mb-3 flex-col items-start gap-1 text-sm">
			<span class="font-semibold">{file} is not valid, so its flow keeps its previous version</span>
			{#each issue.errors.slice(0, 3) as line (line)}<span>{line}</span>{/each}
		</div>
	{/if}
{/each}

{#if !flows}
	<div class="flex justify-center py-20"><span class="loading loading-dots loading-lg text-primary"></span></div>
{:else}
	<div class="grid grid-cols-[repeat(auto-fill,minmax(20rem,1fr))] gap-3">
		{#each flows as f (f.id)}
			<div class="tile flex items-center gap-3 p-3.5" class:is-on={f.enabled} class:opacity-70={!f.enabled}>
				<a href="/automations/flow/{f.id}" class="tile-main flex min-w-0 grow items-center gap-3 rounded-lg after:absolute after:inset-0 after:rounded-[inherit] after:content-['']">
					<span class="icon-bubble"><Icon name="flow" /></span>
					<span class="min-w-0">
						<span class="block truncate font-semibold">{f.name}</span>
						<span class="block truncate text-xs opacity-60">{f.nodes} nodes · last run {ago(f.last_run)}</span>
						{#if f.last_error}<span class="text-error block truncate text-xs">{f.last_error}</span>{/if}
					</span>
				</a>
				{#if f.manual}<button class="btn btn-sm btn-primary relative z-10 shrink-0" onclick={() => run(f)}>Run</button>{/if}
				<input type="checkbox" class="toggle toggle-primary relative z-10 shrink-0" checked={f.enabled}
					aria-label="Enabled" onchange={(e) => setEnabled(f, e.currentTarget.checked)} />
			</div>
		{:else}
			<p class="text-sm opacity-60">No flows yet. Press New flow to start.</p>
		{/each}
	</div>
{/if}

<dialog bind:this={templateDialog} class="modal modal-bottom sm:modal-middle">
	<div class="modal-box flex flex-col overflow-hidden">
		{#if !template}
			<h3 class="mb-3 shrink-0 text-lg font-bold">New flow</h3>
			<div class="flex min-h-0 flex-col gap-2 overflow-y-auto">
				<button class="btn btn-primary justify-start" onclick={blankFlow}><Icon name="plus" class="size-4" />Start from scratch</button>
				<p class="mt-2 text-sm font-semibold opacity-70">Or start from a template</p>
				{#each TEMPLATES as t (t.id)}
					<button class="card bg-base-100 border-base-300 hover:border-primary border p-3 text-left" onclick={() => startTemplate(t)}>
						<span class="font-semibold">{t.title}</span>
						<span class="text-sm opacity-70">{t.blurb}</span>
					</button>
				{/each}
			</div>
			<div class="modal-action shrink-0"><button class="btn" onclick={() => templateDialog?.close()}>Cancel</button></div>
		{:else}
			<h3 class="shrink-0 text-lg font-bold">{template.title}</h3>
			<p class="mb-4 shrink-0 text-sm opacity-70">{template.blurb}</p>
			<div class="flex min-h-0 flex-col gap-3 overflow-y-auto">
				{#each options(template) as { pick, list } (pick.id)}
					<label class="floating-label">
						<span>{pick.label}</span>
						<select class="select w-full" bind:value={chosen[pick.id]}>
							<option value="" disabled>{list.length ? 'Pick one' : `No ${pick.label.toLowerCase()} found`}</option>
							{#each list as c (c.device.id)}<option value={c.device.id}>{c.device.name}{c.device.area ? ` (${c.device.area})` : ''}</option>{/each}
						</select>
					</label>
				{/each}
			</div>
			<div class="modal-action shrink-0">
				<button class="btn" onclick={() => (template = null)}>Back</button>
				<button class="btn btn-primary" disabled={!ready} onclick={useTemplate}>Create flow</button>
			</div>
		{/if}
	</div>
	<form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>

<dialog bind:this={aiDialog} class="modal modal-bottom sm:modal-middle">
	<div class="modal-box flex max-w-xl flex-col overflow-hidden">
		<h3 class="mb-3 shrink-0 text-lg font-bold">Connect an AI</h3>
		<div class="min-h-0 overflow-y-auto"><ConnectAi /></div>
		<div class="modal-action shrink-0"><button class="btn" onclick={() => aiDialog?.close()}>Close</button></div>
	</div>
	<form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>
