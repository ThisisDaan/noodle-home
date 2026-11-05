<script lang="ts">
	import { fly, scale } from 'svelte/transition';
	import Icon from '../Icon.svelte';
	import { api, ApiError } from '../api.ts';
	import { live } from '../live.svelte.ts';
	import type { Integration, SearchState } from './types.ts';

	/** The one screen for adding devices, the same for every integration that can search (IntegrationForm shows it).
	 * Nothing searches until the button is pressed, then for half a minute; the server pushes what it finds (nothing
	 * is polled). Things that need a button pressed (Philips Hue) get the same "press the button" step. */
	let { item, onchange }: { item: Integration; onchange: (updated: Integration) => void } = $props();
	const id = $derived(item.id);
	const noun = $derived(item.noun ?? 'devices');
	const initial = $derived(item.search as SearchState | undefined);

	const mountedAt = Date.now();
	const search = $derived(live.discovery[id] ?? (initial ? { ...initial, at: mountedAt } : undefined));
	const searching = $derived(!!search?.searching);
	const found = $derived(search?.found ?? []);

	// A clock for the countdown, running only while a search does.
	let now = $state(Date.now());
	$effect(() => {
		if (!searching) return;
		now = Date.now();
		const timer = setInterval(() => (now = Date.now()), 250);
		return () => clearInterval(timer);
	});
	const left = $derived(search ? Math.max(0, search.remaining - (now - search.at) / 1000) : 0);
	const progress = $derived(search?.total ? Math.min(1, 1 - left / search.total) : 0);

	let busy = $state<string | null>(null);
	let error = $state('');

	async function run(work: () => Promise<unknown>, what: string) {
		busy = what;
		error = '';
		try {
			await work();
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = null;
		}
	}
	const start = () => run(() => api(`/integrations/${id}/search`, { body: {} }), 'search');
	const stop = () => run(() => api(`/integrations/${id}/search`, { method: 'DELETE' }), 'stop');
	const url = (key: string) => `/integrations/${id}/found/${encodeURIComponent(key)}/add`;

	// Adding may need a button pressed on the device: the server answers 409 until it was, so ask again each second.
	const PRESS_SECONDS = 30;
	let press = $state<{ key: string; left: number; message: string } | null>(null);
	let attempt = 0; // bumped to cancel a wait that is still running
	$effect(() => () => void attempt++);

	async function add(key: string) {
		const mine = ++attempt;
		const end = Date.now() + PRESS_SECONDS * 1000;
		error = '';
		busy = key;
		try {
			while (mine === attempt) {
				try {
					onchange(await api<Integration>(url(key), { body: {} }));
					press = null;
					return;
				} catch (err) {
					if (!(err instanceof ApiError && err.status === 409)) throw err;
					press = { key, left: Math.max(0, Math.ceil((end - Date.now()) / 1000)), message: err.message };
				}
				if (Date.now() >= end) throw new Error('The button was not pressed in time.');
				await new Promise((r) => setTimeout(r, 1000));
			}
		} catch (err) {
			if (mine === attempt) {
				press = null;
				error = err instanceof Error ? err.message : String(err);
			}
		} finally {
			if (mine === attempt) busy = null;
		}
	}
	const cancelPress = () => {
		attempt++;
		press = null;
		busy = null;
	};

	// Spread the dots that mark what was found around the radar, always in the same places for the same key.
	function spot(key: string) {
		let hash = 0;
		for (const ch of key) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
		const angle = ((hash % 360) * Math.PI) / 180;
		const radius = 32 + (hash % 5) * 7;
		return `left:${50 + Math.cos(angle) * radius}%;top:${50 + Math.sin(angle) * radius}%`;
	}
</script>

<div class="flex flex-col gap-3">
	<div class="flex items-center gap-4">
		<div class="radar" class:on={searching} aria-hidden="true">
			<span class="ring r1"></span><span class="ring r2"></span><span class="ring r3"></span>
			<span class="sweep"></span>
			<span class="core"><Icon name="wifi" class="size-6" /></span>
			{#each found as f (f.key)}
				<span class="blip" class:added={f.added} style={spot(f.key)} in:scale={{ duration: 350, start: 0.2 }}></span>
			{/each}
		</div>
		<div class="min-w-0 grow">
			{#if searching}
				<p class="font-medium">Looking for {noun}…</p>
				<p class="text-sm opacity-70">{Math.ceil(left)} s left · found {found.length}</p>
				<progress class="progress progress-primary mt-2 w-full" value={progress} max="1"></progress>
			{:else if search && search.total && found.length}
				<p class="font-medium">Search finished</p>
				<p class="text-sm opacity-70">Found {found.length}. Add the ones you want, or search again.</p>
			{:else if search && search.total}
				<p class="font-medium">Nothing found</p>
				<p class="text-sm opacity-70">Check that the {noun} are switched on and on this network, then search again.</p>
			{:else}
				<p class="font-medium">Add {noun}</p>
				<p class="text-sm opacity-70">Search runs for 30 seconds, only when you press the button.</p>
			{/if}
		</div>
		{#if searching}
			<button type="button" class="btn btn-ghost btn-sm" disabled={busy === 'stop'} onclick={stop}>Stop</button>
		{:else}
			<button type="button" class="btn btn-primary btn-sm" disabled={busy === 'search'} onclick={start}>
				<Icon name="search" class="size-4" />{search?.total ? 'Search again' : 'Search'}
			</button>
		{/if}
	</div>

	{#if searching && item.search_hint}
		<p class="bg-base-200 rounded-box p-3 text-sm">{item.search_hint}</p>
	{/if}

	{#if press}
		<div class="bg-base-200 rounded-box flex flex-col items-center gap-3 p-5 text-center" role="status">
			<p class="font-medium">{item.press_hint || press.message}</p>
			<div class="relative grid size-28 place-items-center">
				<span class="bg-primary/40 absolute inline-flex size-24 animate-ping rounded-full"></span>
				<span class="bg-primary/20 absolute inline-flex size-28 animate-pulse rounded-full"></span>
				<span class="bg-primary text-primary-content relative grid size-20 place-items-center rounded-full text-sm font-bold">Press</span>
			</div>
			<progress class="progress progress-primary w-full" value={PRESS_SECONDS - press.left} max={PRESS_SECONDS}></progress>
			<p class="text-xs opacity-60">Waiting for the button… {press.left}s left</p>
			<button type="button" class="btn btn-ghost btn-sm" onclick={cancelPress}>Cancel</button>
		</div>
	{:else if found.length}
		<ul class="flex flex-col gap-1" aria-live="polite">
			{#each found as f (f.key)}
				<li class="bg-base-200 rounded-box flex items-center gap-3 p-3" in:fly={{ y: 10, duration: 250 }}>
					<span class="min-w-0 grow">
						<span class="block truncate font-medium">{f.name}</span>
						{#if f.detail}<span class="block truncate text-xs opacity-60">{f.detail}</span>{/if}
					</span>
					{#if f.added}
						<span class="text-success flex items-center gap-1 text-sm"><Icon name="check" class="size-4" />Added</span>
					{:else}
						<button type="button" class="btn btn-primary btn-sm" disabled={busy !== null} onclick={() => add(f.key)}>Add</button>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
	{#if search?.error}<div role="alert" class="alert alert-error alert-soft text-sm">Search failed: {search.error}</div>{/if}
	{#if error}<div role="alert" class="alert alert-error alert-soft text-sm">{error}</div>{/if}
</div>

<style>
	.radar {
		position: relative;
		flex: none;
		width: 7rem;
		height: 7rem;
		border-radius: 50%;
		border: 1px solid color-mix(in oklab, var(--color-primary) 25%, transparent);
		background: radial-gradient(circle, color-mix(in oklab, var(--color-primary) 10%, transparent), transparent 70%);
	}
	.core {
		position: absolute;
		inset: 50% auto auto 50%;
		translate: -50% -50%;
		display: grid;
		place-items: center;
		width: 2.75rem;
		height: 2.75rem;
		border-radius: 50%;
		background: var(--color-primary);
		color: var(--color-primary-content);
	}
	.ring {
		position: absolute;
		inset: 0;
		border-radius: 50%;
		border: 2px solid var(--color-primary);
		opacity: 0;
	}
	.sweep {
		position: absolute;
		inset: 0;
		border-radius: 50%;
		background: conic-gradient(from 0deg, transparent 0 70%, color-mix(in oklab, var(--color-primary) 45%, transparent));
		opacity: 0;
	}
	.blip {
		position: absolute;
		width: 0.6rem;
		height: 0.6rem;
		translate: -50% -50%;
		border-radius: 50%;
		background: var(--color-warning);
		box-shadow: 0 0 0 3px color-mix(in oklab, var(--color-warning) 30%, transparent);
	}
	.blip.added {
		background: var(--color-success);
		box-shadow: 0 0 0 3px color-mix(in oklab, var(--color-success) 30%, transparent);
	}
	@media (prefers-reduced-motion: no-preference) {
		.on .ring {
			animation: ping 2.4s cubic-bezier(0.2, 0.6, 0.4, 1) infinite;
		}
		.on .r2 {
			animation-delay: 0.8s;
		}
		.on .r3 {
			animation-delay: 1.6s;
		}
		.on .sweep {
			opacity: 1;
			animation: spin 2s linear infinite;
		}
		.on .core {
			animation: beat 1.2s ease-in-out infinite;
		}
		.blip {
			animation: blip 1.8s ease-in-out infinite;
		}
		.blip.added {
			animation: none;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.on .ring.r1 {
			opacity: 0.4;
		}
	}
	@keyframes ping {
		0% {
			transform: scale(0.35);
			opacity: 0.6;
		}
		100% {
			transform: scale(1.15);
			opacity: 0;
		}
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	@keyframes beat {
		50% {
			transform: scale(1.08);
		}
	}
	@keyframes blip {
		50% {
			box-shadow: 0 0 0 7px color-mix(in oklab, var(--color-warning) 5%, transparent);
		}
	}
</style>
