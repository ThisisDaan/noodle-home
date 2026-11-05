<script lang="ts">
	import { api, type Device, type Entity } from '../api.ts';
	import { lastChanges } from './last.svelte.ts';

	/** A button or remote: which button was pressed last and when. In the large version every press can be
	 * tested from here: it counts as a real press (shows up in the history and runs the automations). */
	let { device, size = 'tile' }: { device: Device; size?: 'tile' | 'large' } = $props();

	const last = lastChanges(() => device.id);
	const buttons = $derived(device.entities.filter((e) => e.kind === 'button'));
	const words = (text: unknown) => String(text ?? '').replaceAll('_', ' ');

	// The press shown on the tile: the newest one across all buttons of the device.
	const newest = $derived(
		buttons
			.map((e) => ({ e, at: last.get(e.key) }))
			.filter((x) => x.at)
			.sort((a, b) => b.at!.ts - a.at!.ts)[0]
	);

	let pressing = $state<string | null>(null);
	let error = $state('');
	async function press(entity: Entity, action: string) {
		pressing = `${entity.key}:${action}`;
		error = '';
		try {
			await api(`/devices/${encodeURIComponent(device.id)}/entities/${encodeURIComponent(entity.key)}/press`, { body: { action } });
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			setTimeout(() => (pressing = null), 300);
		}
	}
	const main = (e: Entity) => e.actions?.find((a) => /^(single|press|short_release|initial_press)$/.test(a)) ?? e.actions?.[0];

	// Buttons of a multi-button remote that belong together are listed under one heading.
	const groups = $derived.by(() => {
		const out: { title: string | null; items: Entity[] }[] = [];
		for (const e of buttons) {
			const title = e.group ?? null;
			const group = out.find((g) => g.title === title);
			if (group) group.items.push(e);
			else out.push({ title, items: [e] });
		}
		return out;
	});
</script>

{#if size === 'large'}
	<div class="flex flex-col gap-3" class:opacity-50={!device.available}>
		{#each groups as g (g.title ?? '')}
			<div class="bg-base-200 rounded-box flex flex-col gap-3 p-3.5">
				{#if g.title}<h4 class="text-xs font-semibold tracking-wide uppercase opacity-60">{g.title}</h4>{/if}
				{#each g.items as e (e.key)}
					<div class="flex flex-col gap-2">
						<div class="flex items-baseline justify-between gap-3">
							<span class="font-medium">{e.name}</span>
							<span class="truncate text-xs opacity-60">
								{last.get(e.key) ? `${words(last.get(e.key)!.value)} · ${last.ago(e.key)}` : 'never used'}
							</span>
						</div>
						<div class="flex flex-wrap gap-2">
							{#each e.actions?.length ? e.actions : ['single'] as action (action)}
								<button type="button" class="btn btn-sm active:scale-95 {pressing === `${e.key}:${action}` ? 'btn-primary' : 'btn-soft'}"
									disabled={!device.available} onclick={() => press(e, action)}>{words(action)}</button>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		{/each}
		<p class="text-xs opacity-60">A press here is treated as a real one: automations that listen to this button run.</p>
		{#if error}<div role="alert" class="alert alert-error alert-soft text-sm">{error}</div>{/if}
	</div>
{:else}
	<div class="flex items-center gap-2 text-sm" class:opacity-50={!device.available}>
		<span class="min-w-0 grow">
			{#if newest}
				<span class="block truncate font-semibold">{words(newest.at!.value)}</span>
				<span class="block truncate text-xs opacity-60">{buttons.length > 1 ? `${newest.e.name} · ` : ''}{last.ago(newest.e.key)}</span>
			{:else}
				<span class="opacity-60">Not used yet</span>
			{/if}
		</span>
		{#if buttons.length === 1 && main(buttons[0]) && device.available}
			<button type="button" class="btn btn-sm btn-circle btn-soft relative z-10 active:scale-90" aria-label="Press {buttons[0].name}"
				onclick={(e) => { e.stopPropagation(); press(buttons[0], main(buttons[0])!); }}>
				<span class="size-3 rounded-full bg-current"></span>
			</button>
		{/if}
	</div>
{/if}
