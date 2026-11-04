<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import { api, ApiError } from '#lib/api.ts';
	import DeviceSheet from '#lib/DeviceSheet.svelte';
	import GroupDialog from '#lib/GroupDialog.svelte';
	import Icon from '#lib/Icon.svelte';
	import Logo from '#lib/Logo.svelte';
	import Wizard from '#lib/Wizard.svelte';
	import { layout } from '#lib/layout.svelte.ts';
	import { live } from '#lib/live.svelte.ts';

	let { children } = $props();

	type Status = { setup_needed: boolean; logged_in: boolean; wizard?: boolean };
	let status = $state<Status | null>(null);
	let password = $state('');
	let confirm = $state('');
	let error = $state('');
	let busy = $state(false);

	const links = [
		{ href: '/', label: 'Dashboard', icon: 'home' },
		{ href: '/devices', label: 'Devices', icon: 'devices' },
		{ href: '/automations', label: 'Automations', icon: 'flow' },
		{ href: '/integrations', label: 'Integrations', icon: 'plug' },
		{ href: '/system', label: 'System', icon: 'system' }
	];
	const isActive = (href: string) => (href === '/' ? page.url.pathname === '/' : page.url.pathname.startsWith(href));

	async function refresh() {
		status = await api<Status>('/auth/status');
		if (status.logged_in) {
			live.start();
			layout.load();
		} else live.stop();
	}

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		if (status?.setup_needed && password !== confirm) {
			error = 'Passwords do not match';
			return;
		}
		busy = true;
		try {
			await api(status?.setup_needed ? '/auth/setup' : '/auth/login', { body: { password } });
			password = confirm = '';
			await refresh();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Something went wrong';
		} finally {
			busy = false;
		}
	}

	async function logout() {
		await api('/auth/logout', { body: {} });
		await refresh();
	}

	$effect(() => {
		refresh();
	});
</script>

<svelte:head><title>{live.homeName ? `${live.homeName} · Noodle` : 'Noodle'}</title></svelte:head>

{#if status === null}
	<div class="flex min-h-screen items-center justify-center">
		<span class="loading loading-spinner loading-lg text-primary"></span>
	</div>
{:else if !status.logged_in}
	<div class="flex min-h-screen items-center justify-center p-4">
		<form class="card bg-base-100 border-base-content/10 w-full max-w-sm border shadow-xl" onsubmit={submit}>
			<div class="card-body gap-4">
				<Logo class="size-14" />
				<div>
					<h1 class="text-2xl font-bold">Noodle</h1>
					<p class="text-sm opacity-70">
						{status.setup_needed ? 'Choose a password for this hub (at least 8 characters).' : 'Welcome back. Log in to continue.'}
					</p>
				</div>
				<label class="floating-label">
					<span>Password</span>
					<input class="input w-full" type="password" placeholder="Password" bind:value={password}
						autocomplete={status.setup_needed ? 'new-password' : 'current-password'} minlength="8" required />
				</label>
				{#if status.setup_needed}
					<label class="floating-label">
						<span>Repeat password</span>
						<input class="input w-full" type="password" placeholder="Repeat password" bind:value={confirm}
							autocomplete="new-password" minlength="8" required />
					</label>
				{/if}
				{#if error}<div role="alert" class="alert alert-error alert-soft text-sm">{error}</div>{/if}
				<button class="btn btn-primary" disabled={busy}>
					{#if busy}<span class="loading loading-spinner loading-sm"></span>{/if}
					{status.setup_needed ? 'Set password' : 'Log in'}
				</button>
			</div>
		</form>
	</div>
{:else}
	<aside class="bg-base-100/80 border-base-content/10 fixed inset-y-0 left-0 z-20 hidden w-60 flex-col gap-1 border-r p-4 backdrop-blur lg:flex">
		<a href="/" class="mb-6 flex items-center gap-3 px-1">
			<Logo class="size-10" />
			<span class="min-w-0 truncate text-lg font-bold tracking-tight">{live.homeName || 'Noodle'}</span>
		</a>
		{#each links as link (link.href)}
			<a href={link.href} class="nav-link" class:active={isActive(link.href)} aria-current={isActive(link.href) ? 'page' : undefined}>
				<Icon name={link.icon} />{link.label}
			</a>
		{/each}
		<div class="mt-auto flex items-center gap-2 px-1">
			<span class="status" class:status-success={live.connected} class:status-warning={!live.connected}></span>
			<span class="grow text-sm opacity-70">{live.connected ? 'Live' : 'Reconnecting…'}</span>
			<button class="btn btn-ghost btn-sm btn-square" onclick={logout} aria-label="Log out"><Icon name="logout" /></button>
		</div>
	</aside>

	<header class="bg-base-100/80 border-base-content/10 sticky top-0 z-10 flex items-center gap-3 border-b px-4 py-2.5 backdrop-blur lg:hidden">
		<Logo class="size-9" />
		<span class="min-w-0 grow truncate text-lg font-bold tracking-tight">{live.homeName || 'Noodle'}</span>
		<span class="status" class:status-success={live.connected} class:status-warning={!live.connected}></span>
		<button class="btn btn-ghost btn-sm btn-square" onclick={logout} aria-label="Log out"><Icon name="logout" /></button>
	</header>

	<main class="min-h-screen px-4 pt-5 pb-28 lg:pb-10 lg:pl-[17rem] lg:pr-8">
		<div class="mx-auto max-w-[110rem]">{@render children()}</div>
	</main>

	<nav class="dock lg:hidden" aria-label="Main">
		{#each links as link (link.href)}
			<a href={link.href} class:dock-active={isActive(link.href)} aria-label={link.label}>
				<Icon name={link.icon} />
				<span class="dock-label">{link.label}</span>
			</a>
		{/each}
	</nav>

	<DeviceSheet />
	<GroupDialog />
	{#if status.wizard}<Wizard onfinish={refresh} />{/if}
{/if}
