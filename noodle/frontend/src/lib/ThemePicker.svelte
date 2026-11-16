<script lang="ts">
	import { api } from '#lib/api.ts';
	import { live } from '#lib/live.svelte.ts';
	import { known, THEMES } from '#lib/theme.ts';

	// The hub's theme, for every phone and computer: picking one applies and saves it straight away.

	let error = $state('');
	let saving = $state(false);

	async function choose(id: string) {
		const before = live.theme;
		live.theme = id; // show it at once
		saving = true;
		error = '';
		try {
			const res = await api<{ theme: string }>('/theme', { method: 'PUT', body: { theme: id } });
			live.theme = known(res.theme);
		} catch (err) {
			live.theme = before;
			error = err instanceof Error ? err.message : String(err);
		} finally {
			saving = false;
		}
	}
</script>

<div class="flex flex-col gap-3">
	<label class="floating-label">
		<span>Theme</span>
		<select class="select select-sm w-full max-w-xs" value={live.theme ?? ''} disabled={live.theme === undefined || saving}
			onchange={(e) => choose(e.currentTarget.value)}>
			<option value="">Noodle (follows light or dark mode)</option>
			<optgroup label="Light">
				{#each THEMES.filter((t) => !t.dark) as t (t.id)}<option value={t.id}>{t.label}</option>{/each}
			</optgroup>
			<optgroup label="Dark">
				{#each THEMES.filter((t) => t.dark) as t (t.id)}<option value={t.id}>{t.label}</option>{/each}
			</optgroup>
		</select>
	</label>
	<p class="text-xs opacity-60">For the whole hub: every phone and computer changes straight away.</p>

	<!-- How the theme looks, with every colour it has. -->
	<div class="bg-base-200 rounded-box p-3">
		<div class="card bg-base-100 shadow-sm">
			<div class="card-body gap-3 p-4">
				<div class="flex items-center justify-between gap-2">
					<span class="font-semibold">Living room lamp</span>
					<input type="checkbox" class="toggle toggle-primary toggle-sm" checked aria-label="Example switch" />
				</div>
				<div class="flex flex-wrap gap-1">
					<span class="badge badge-success badge-sm">Connected</span>
					<span class="badge badge-warning badge-sm">Low battery</span>
					<span class="badge badge-error badge-sm">Offline</span>
					<span class="badge badge-info badge-sm">Tip</span>
					<span class="badge badge-accent badge-sm">New</span>
				</div>
				<div class="flex flex-wrap gap-2">
					<button class="btn btn-primary btn-sm" tabindex="-1">Primary</button>
					<button class="btn btn-secondary btn-sm" tabindex="-1">Secondary</button>
					<button class="btn btn-sm" tabindex="-1">Plain</button>
				</div>
			</div>
		</div>
	</div>
	{#if error}<div role="alert" class="alert alert-error alert-soft text-sm">{error}</div>{/if}
</div>
