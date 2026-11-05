<script lang="ts">
	import { api, type Device, type Entity } from '../api.ts';
	import Icon from '../Icon.svelte';
	import DialControl from './DialControl.svelte';

	/** A button or remote on a card: it acts like the button. Pressing it counts as a real press (it shows in the
	 * history and runs the automations that listen to it). Every remote with a dimmer pair (inputs the hub marked
	 * "increase" and "decrease": a wheel, Brighter and Dimmer, ...) gets the same − knob +, one profile at a time
	 * with a switch for the profile; its other buttons (On, Off, ...) sit beside it. Any other button is a round
	 * button of its own. */
	let { device }: { device: Device } = $props();

	// Numbered buttons in numeric order (1 2 3 4, not the order the bridge happens to list them in).
	const buttons = $derived(
		device.entities.filter((e) => e.kind === 'button').sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))
	);
	let pressed = $state<string | null>(null);
	let error = $state('');
	let profile = $state(0);

	const main = (e: Entity) => e.actions?.find((a) => /^(single|press|short_release|initial_press)$/.test(a)) ?? e.actions?.[0] ?? 'single';
	const label = (e: Entity) => e.name.replace(/^Button\s*/i, '') || e.name;

	const press = (entity: Entity) => pressAction(entity, main(entity));
	async function pressAction(entity: Entity, action: string) {
		pressed = entity.key;
		error = '';
		try {
			await api(`/devices/${encodeURIComponent(device.id)}/entities/${encodeURIComponent(entity.key)}/press`, { body: { action } });
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			setTimeout(() => (pressed = null), 250);
		}
	}

	// One input that reports single / double / triple (a tap switch): one button, tapped once, twice or three
	// times within a moment, like the real one. The press is sent once the taps stop.
	const TAPS = ['single', 'double', 'triple'];
	const multiTap = $derived(buttons.length === 1 && TAPS.filter((a) => buttons[0].actions?.includes(a)).length > 1);
	let taps = 0;
	let tapTimer: ReturnType<typeof setTimeout> | undefined;
	function tap(entity: Entity) {
		const allowed = TAPS.filter((a) => entity.actions?.includes(a));
		taps = Math.min(taps + 1, allowed.length);
		clearTimeout(tapTimer);
		tapTimer = setTimeout(() => {
			const action = allowed[taps - 1];
			taps = 0;
			pressAction(entity, action);
		}, 350);
	}

	// The inputs of one profile of a remote stay together: the dimmer pair (by role) and what else it has.
	type Section = { title: string | null; down?: Entity; up?: Entity; others: Entity[] };
	const sections = $derived.by(() => {
		const out: Section[] = [];
		for (const e of buttons) {
			const title = e.group ?? null;
			let section = out.find((s) => s.title === title);
			if (!section) out.push((section = { title, others: [] }));
			if (e.role === 'decrease' && !section.down) section.down = e;
			else if (e.role === 'increase' && !section.up) section.up = e;
			else section.others.push(e);
		}
		return out;
	});
	const hasDial = $derived(sections.some((s) => s.down && s.up));
	const current = $derived(sections[Math.min(profile, sections.length - 1)]);
</script>

{#if buttons.length && device.available}
	{#if multiTap}
		<button type="button" class="btn rounded-box h-12 min-h-0 w-full gap-2 active:scale-[0.97] {pressed ? 'btn-primary' : 'btn-soft'}"
			aria-label="Press {device.name}: tap once, twice or three times" onclick={() => tap(buttons[0])}>
			<Icon name="circle" class="size-5" />Press
		</button>
	{:else if buttons.length === 1 && (buttons[0].actions?.length ?? 0) > 1 && !buttons[0].actions!.some((a) => /multi_press|long_press/.test(a))}
		<!-- One input that reports several presses (a Zigbee dimmer's on, up, down, off): a button for each. -->
		<div class="flex h-12 gap-2 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" role="group" aria-label="Presses of {device.name}">
			{#each buttons[0].actions!.filter((a) => !/release|hold/.test(a)) as action (action)}
				<button type="button" class="btn btn-soft rounded-box h-12 min-h-0 flex-none px-3 capitalize active:scale-90"
					onclick={() => pressAction(buttons[0], action)}>{action.replace(/_press$/, '').replaceAll('_', ' ')}</button>
			{/each}
		</div>
	{:else if buttons.length === 1}
		<button type="button" class="btn btn-soft rounded-box h-12 min-h-0 w-full gap-2 active:scale-[0.97]" onclick={() => press(buttons[0])}>
			<Icon name="circle" class="size-5" />Press
		</button>
	{:else if hasDial && current}
		<div class="flex h-12 items-center gap-2">
			{#if current.down && current.up}
				<DialControl label={current.title ?? device.name}
					onstep={(direction) => press(direction > 0 ? current.up! : current.down!)}
					ontap={current.others.length === 1 ? () => press(current.others[0]) : undefined} />
			{/if}
			{#if current.others.length > 1}
				{#each current.others as e (e.key)}
					<button type="button" title={e.name} aria-label="Press {e.name}"
						class="btn h-12 min-h-0 min-w-0 flex-1 rounded-full px-2 text-xs active:scale-90 {pressed === e.key ? 'btn-primary' : 'btn-soft'}"
						onclick={() => press(e)}>{e.name}</button>
				{/each}
			{/if}
			{#if sections.length > 1}
				<div class="join h-12 min-w-0 grow" role="group" aria-label="Profile">
					{#each sections as s, i (s.title ?? i)}
						<button type="button" title={s.title ?? ''} aria-pressed={i === profile}
							class="btn join-item h-12 min-h-0 min-w-0 flex-1 px-0 {i === profile ? 'btn-primary' : 'btn-soft'}"
							onclick={() => (profile = i)}>{s.title?.replace(/\D+/g, '') || i + 1}</button>
					{/each}
				</div>
			{/if}
		</div>
	{:else}
		<div class="flex h-12 gap-2 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" role="group" aria-label="Buttons of {device.name}">
			{#each buttons as e (e.key)}
				<button type="button" title={e.name} aria-label="Press {e.name}"
					class="btn rounded-box h-12 min-h-0 min-w-12 flex-1 px-3 active:scale-90 {pressed === e.key ? 'btn-primary' : 'btn-soft'}"
					onclick={() => press(e)}>{label(e)}</button>
			{/each}
		</div>
	{/if}
	{#if error}<p class="text-error absolute right-3 bottom-0.5 text-xs">{error}</p>{/if}
{/if}
