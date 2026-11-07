<script lang="ts">
	import Icon from './Icon.svelte';
	import { iconFor, isOn } from './api.ts';
	import CardBody from './devices/CardBody.svelte';
	import TileSubtitle from './devices/TileSubtitle.svelte';
	import {
		COMPONENTS, HOURS, MAX_H, MAX_W, PRESETS, STYLES, autoStyle, compatible, defaultDesign, freeSpot, grid, hoursLabel, minSize,
		placeable, presetFields, startSize, stylesFor, type CardDesign, type CardSlot, type CardStyle
	} from './devices/cardDesign.ts';
	import { motionActive } from './devices/kinds.ts';
	import { cardDesigner } from './designer.svelte';
	import { layout } from './layout.svelte';
	import { live } from './live.svelte';

	// The card is drawn at its real size on a stage that shows the dashboard's cells. These are the sizes of a cell
	// there (16rem x 9rem with 0.75rem between), in px; the stage shrinks to fit a small window.
	const CELL_W = 256, CELL_H = 144, GAP = 12, BODY_GAP = 6;
	const STAGE_W = MAX_W * CELL_W + (MAX_W - 1) * GAP;
	const STAGE_H = MAX_H * CELL_H + (MAX_H - 1) * GAP;

	let dialog: HTMLDialogElement;
	const device = $derived(cardDesigner.deviceId ? live.devices[cardDesigner.deviceId] : undefined);
	let draft = $state<CardDesign>({ w: 1, h: 1, slots: [] });
	let selected = $state<number | null>(null);
	let note = $state('');
	let bodyEl = $state<HTMLElement>();
	let available = $state(STAGE_W);
	const scale = $derived(Math.max(0.6, Math.min(1, (available - 48) / STAGE_W)));

	$effect(() => {
		if (device && !dialog.open) {
			// Open on what the card looks like now: the saved design, else the device's own look written as a design.
			const start = layout.cards[device.id] ?? defaultDesign(device);
			draft = start
				? { w: start.w, h: start.h, slots: start.slots.map((s) => ({ ...s, ...(s.component === 'value' ? { style: s.style ?? autoStyle(device.entities.find((e) => e.key === s.key)) } : {}) })) }
				: { w: 1, h: 1, slots: [] };
			selected = null;
			note = '';
			dialog.showModal();
		}
		if (!device && dialog?.open) dialog.close();
	});

	const sel = $derived(selected !== null ? draft.slots[selected] : undefined);
	const entity = $derived(sel ? device?.entities.find((e) => e.key === sel.key) : undefined);
	const fields = $derived(sel && device ? device.entities.filter((e) => compatible(sel.component, e)) : []);
	const styles = $derived(entity ? stylesFor(entity) : []);
	const cardPx = $derived({ w: draft.w * CELL_W + (draft.w - 1) * GAP, h: draft.h * CELL_H + (draft.h - 1) * GAP });
	const fieldName = (k: string) => device?.entities.find((e) => e.key === k)?.name ?? k;

	// --- adding, changing, removing ---
	function add(p: (typeof PRESETS)[number]) {
		if (!device) return;
		const choices = presetFields(device, p);
		if (!choices.length) return;
		const used = new Set(draft.slots.map((s) => s.key));
		const e = choices.find((c) => !used.has(c.key)) ?? choices[0];
		const want = startSize(p.component, p.style);
		// the size it likes, else the biggest that still fits somewhere
		for (let w = want.w; w >= 1; w--) {
			for (let h = want.h; h >= 1; h--) {
				const at = freeSpot(draft, w, h);
				if (!at) continue;
				draft.slots.push({ ...at, w, h, component: p.component, key: e.key, ...(p.style ? { style: p.style } : {}) });
				selected = draft.slots.length - 1;
				note = '';
				return;
			}
		}
		note = 'No room left on the card. Make the card bigger or move things.';
	}
	function setField(key: string) {
		if (selected === null || !sel) return;
		const e = device?.entities.find((x) => x.key === key);
		const next: CardSlot = { ...sel, key };
		if (sel.component === 'value' && e && !stylesFor(e).includes(sel.style ?? 'text-l')) next.style = stylesFor(e)[0];
		draft.slots[selected] = next;
	}
	function setStyle(style: CardStyle) {
		if (selected === null || !sel) return;
		const next: CardSlot = { ...sel, style };
		if (STYLES[style].graph) next.hours = sel.hours ?? 6;
		else delete next.hours;
		draft.slots[selected] = next;
	}
	function patch(p: Partial<CardSlot>) {
		if (selected !== null && sel) draft.slots[selected] = { ...sel, ...p };
	}
	function remove() {
		if (selected === null) return;
		draft.slots.splice(selected, 1);
		selected = null;
	}
	function setLabel(text: string) {
		if (selected === null || !sel) return;
		const next: CardSlot = { ...sel, label: text };
		if (!text.trim()) delete next.label;
		draft.slots[selected] = next;
	}
	function setSize(w: number, h: number) {
		const min = minSize(draft);
		const next = { w: Math.min(MAX_W, Math.max(min.w, w)), h: Math.min(MAX_H, Math.max(min.h, h)) };
		if ((w < min.w || h < min.h) && (w !== draft.w || h !== draft.h)) note = 'The card cannot get smaller than the components on it.';
		else note = '';
		draft.w = next.w;
		draft.h = next.h;
	}

	// --- dragging a component (move / resize) and the card itself ---
	type Drag = { index: number; mode: 'move' | 'e' | 's' | 'se'; x0: number; y0: number; orig: CardSlot; px: number; py: number };
	let drag: Drag | null = null;
	function down(e: PointerEvent, index: number, mode: Drag['mode']) {
		selected = index;
		note = '';
		if (e.button !== 0 || !bodyEl) return;
		e.preventDefault();
		const r = bodyEl.getBoundingClientRect(), g = grid(draft), gap = BODY_GAP * scale;
		drag = { index, mode, x0: e.clientX, y0: e.clientY, orig: { ...draft.slots[index] }, px: (r.width + gap) / g.cols, py: (r.height + gap) / g.rows };
		window.addEventListener('pointermove', moveSlot);
		window.addEventListener('pointerup', stop, { once: true });
	}
	function moveSlot(e: PointerEvent) {
		if (!drag) return;
		const g = grid(draft), o = drag.orig;
		const dx = Math.round((e.clientX - drag.x0) / drag.px), dy = Math.round((e.clientY - drag.y0) / drag.py);
		const tries: CardSlot[] = [];
		const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
		if (drag.mode === 'move') {
			const x = clamp(o.x + dx, 0, g.cols - o.w), y = clamp(o.y + dy, 0, g.rows - o.h);
			tries.push({ ...o, x, y }, { ...o, x }, { ...o, y }); // blocked diagonally: slide along one axis
		} else {
			tries.push({ ...o, w: drag.mode === 'e' || drag.mode === 'se' ? clamp(o.w + dx, 1, g.cols - o.x) : o.w, h: drag.mode === 's' || drag.mode === 'se' ? clamp(o.h + dy, 1, g.rows - o.y) : o.h });
		}
		const ok = tries.find((t) => placeable(draft, t, drag!.index));
		if (ok) draft.slots[drag.index] = ok;
	}
	function stop() {
		drag = null;
		window.removeEventListener('pointermove', moveSlot);
		window.removeEventListener('pointermove', moveCard);
	}
	let cardDrag: { mode: 'e' | 's' | 'se'; x0: number; y0: number; w: number; h: number } | null = null;
	function downCard(e: PointerEvent, mode: 'e' | 's' | 'se') {
		if (e.button !== 0) return;
		e.preventDefault();
		note = '';
		cardDrag = { mode, x0: e.clientX, y0: e.clientY, w: draft.w, h: draft.h };
		window.addEventListener('pointermove', moveCard);
		window.addEventListener('pointerup', () => { cardDrag = null; stop(); }, { once: true });
	}
	function moveCard(e: PointerEvent) {
		if (!cardDrag) return;
		const dw = cardDrag.mode === 's' ? 0 : Math.round((e.clientX - cardDrag.x0) / scale / (CELL_W + GAP));
		const dh = cardDrag.mode === 'e' ? 0 : Math.round((e.clientY - cardDrag.y0) / scale / (CELL_H + GAP));
		setSize(cardDrag.w + dw, cardDrag.h + dh);
	}
	function key(e: KeyboardEvent) {
		if (selected === null || !sel || (e.target as HTMLElement).closest('input, select, textarea, button')) return;
		const move: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
		if (e.key === 'Delete' || e.key === 'Backspace') {
			e.preventDefault();
			remove();
		} else if (move[e.key]) {
			e.preventDefault();
			const next = e.shiftKey ? { ...sel, w: sel.w + move[e.key][0], h: sel.h + move[e.key][1] } : { ...sel, x: sel.x + move[e.key][0], y: sel.y + move[e.key][1] };
			if (placeable(draft, next, selected)) draft.slots[selected] = next;
		}
	}

	function save() {
		if (!device) return;
		layout.setCard(device.id, draft.slots.length ? $state.snapshot(draft) : null);
		cardDesigner.close();
	}
	function reset() {
		if (!device) return;
		layout.setCard(device.id, null);
		cardDesigner.close();
	}
</script>

<svelte:window onkeydown={key} />

<dialog class="modal" bind:this={dialog} onclose={() => cardDesigner.close()}>
	<div class="modal-box flex h-dvh max-h-none w-screen max-w-none flex-col gap-0 overflow-hidden rounded-none p-0">
		{#if device}
			<div class="border-base-content/10 flex shrink-0 items-center gap-3 border-b px-4 py-3">
				<span class="icon-bubble"><Icon name="edit" /></span>
				<h2 class="min-w-0 grow truncate text-lg font-bold">Design the card of {device.name}</h2>
				{#if layout.cards[device.id]}<button class="btn btn-ghost btn-sm" onclick={reset}>Back to the default look</button>{/if}
				<button class="btn btn-ghost btn-sm" onclick={() => cardDesigner.close()}>Cancel</button>
				<button class="btn btn-primary btn-sm" onclick={save}>Save</button>
			</div>

			<div class="flex min-h-0 grow flex-col lg:flex-row">
				<!-- The stage: the card exactly as it will look, on the cells of the dashboard. Drag the card's edges to make it bigger or smaller. -->
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<div class="bg-base-200 min-h-0 min-w-0 grow overflow-auto p-6" bind:clientWidth={available}
					onpointerdown={(e) => { if (!(e.target as HTMLElement).closest('[data-slot], button')) selected = null; }}>
					<div class="relative" style="width: {STAGE_W * scale}px; height: {STAGE_H * scale}px;">
						<div class="absolute top-0 left-0 origin-top-left" style="width: {STAGE_W}px; height: {STAGE_H}px; transform: scale({scale});">
							{#each Array.from({ length: MAX_W * MAX_H }, (_, i) => i) as i (i)}
								<div class="border-base-content/15 rounded-box absolute border border-dashed"
									style="left: {(i % MAX_W) * (CELL_W + GAP)}px; top: {Math.floor(i / MAX_W) * (CELL_H + GAP)}px; width: {CELL_W}px; height: {CELL_H}px;"></div>
							{/each}
							<div class="tile absolute top-0 left-0 flex flex-col justify-between gap-3 p-3.5" class:is-on={isOn(device) || motionActive(device)}
								style="width: {cardPx.w}px; height: {cardPx.h}px; transform: none;">
								<div class="flex items-start gap-3">
									<span class="icon-bubble"><Icon name={iconFor(device)} /></span>
									<span class="min-w-0">
										<span class="block truncate leading-tight font-semibold">{device.name}</span>
										<span class="block truncate text-xs opacity-60"><TileSubtitle {device} /></span>
									</span>
								</div>
								<div class="min-h-0 grow">
									<CardBody {device} design={draft} labelled bind:el={bodyEl} editor={{ get selected() { return selected; }, down }} />
								</div>
								<!-- svelte-ignore a11y_no_static_element_interactions -->
								<span class="absolute inset-y-4 -right-3.5 w-4 cursor-ew-resize touch-none" onpointerdown={(e) => downCard(e, 'e')}>
									<span class="bg-base-content/40 absolute inset-y-0 left-2 w-1 rounded-full"></span></span>
								<!-- svelte-ignore a11y_no_static_element_interactions -->
								<span class="absolute inset-x-4 -bottom-3.5 h-4 cursor-ns-resize touch-none" onpointerdown={(e) => downCard(e, 's')}>
									<span class="bg-base-content/40 absolute inset-x-0 top-2 h-1 rounded-full"></span></span>
								<!-- svelte-ignore a11y_no_static_element_interactions -->
								<span class="bg-base-content/60 border-base-100 absolute -right-4 -bottom-4 size-5 cursor-nwse-resize touch-none rounded-full border-2" onpointerdown={(e) => downCard(e, 'se')}></span>
							</div>
						</div>
					</div>
				</div>

				<!-- The panel never changes place: what is selected only fills it in. -->
				<aside class="border-base-content/10 flex max-h-[45dvh] shrink-0 flex-col gap-5 overflow-y-auto border-t p-4 lg:max-h-none lg:w-80 lg:border-t-0 lg:border-l">
					<section class="flex flex-col gap-2">
						<h3 class="text-sm font-semibold">Card size</h3>
						<div class="flex items-center gap-2 text-sm">
							<div class="join">
								<button class="btn btn-sm join-item btn-square" aria-label="Narrower" disabled={draft.w <= minSize(draft).w} onclick={() => setSize(draft.w - 1, draft.h)}>−</button>
								<span class="join-item border-base-content/20 grid w-16 place-items-center border text-sm tabular-nums">{draft.w} wide</span>
								<button class="btn btn-sm join-item btn-square" aria-label="Wider" disabled={draft.w >= MAX_W} onclick={() => setSize(draft.w + 1, draft.h)}>+</button>
							</div>
							<div class="join">
								<button class="btn btn-sm join-item btn-square" aria-label="Shorter" disabled={draft.h <= minSize(draft).h} onclick={() => setSize(draft.w, draft.h - 1)}>−</button>
								<span class="join-item border-base-content/20 grid w-16 place-items-center border text-sm tabular-nums">{draft.h} high</span>
								<button class="btn btn-sm join-item btn-square" aria-label="Taller" disabled={draft.h >= MAX_H} onclick={() => setSize(draft.w, draft.h + 1)}>+</button>
							</div>
						</div>
						<p class="text-xs opacity-60">Or drag the card's edge or corner.</p>
					</section>

					<section class="flex flex-col gap-2">
						<h3 class="text-sm font-semibold">Add to the card</h3>
						<div class="grid grid-cols-3 gap-2">
							{#each PRESETS as p (p.id)}
								<button class="btn btn-sm btn-soft" disabled={!presetFields(device, p).length} onclick={() => add(p)}>{p.label}</button>
							{/each}
						</div>
						<p class="min-h-8 text-xs opacity-70" role="status">{note}</p>
					</section>

					<section class="flex min-h-64 flex-col gap-3">
						<h3 class="text-sm font-semibold">{sel ? (sel.component === 'value' ? 'Reading' : COMPONENTS[sel.component].label) : 'Selected'}</h3>
						{#if sel && entity}
							<label class="flex flex-col gap-1 text-xs font-medium opacity-80">Shows
								<select class="select select-sm w-full" value={sel.key} onchange={(e) => setField(e.currentTarget.value)}>
									{#each fields as f (f.key)}<option value={f.key}>{f.name}</option>{/each}
								</select>
							</label>
							{#if sel.component === 'value'}
								<div class="flex flex-col gap-1 text-xs font-medium opacity-80">Looks like
									<div class="grid grid-cols-2 gap-1.5">
										{#each styles as s (s)}
											<button class="btn btn-xs" class:btn-primary={sel.style === s} onclick={() => setStyle(s)}>{STYLES[s].label}</button>
										{/each}
									</div>
								</div>
								{#if sel.style && STYLES[sel.style].graph}
									<label class="flex flex-col gap-1 text-xs font-medium opacity-80">History
										<select class="select select-sm w-full" value={sel.hours ?? 6} onchange={(e) => patch({ hours: Number(e.currentTarget.value) })}>
											{#each HOURS as h (h)}<option value={h}>Last {hoursLabel(h)}</option>{/each}
										</select>
									</label>
								{/if}
							{/if}
							<label class="flex flex-col gap-1 text-xs font-medium opacity-80">Name on the card
								<input class="input input-sm w-full" value={sel.label ?? ''} placeholder={fieldName(sel.key)} maxlength="40" oninput={(e) => setLabel(e.currentTarget.value)} />
							</label>
							<button class="btn btn-sm btn-error btn-outline mt-auto" onclick={remove}><Icon name="close" class="size-4" />Remove</button>
						{:else}
							<p class="text-sm opacity-60">Tap a component on the card to change what it shows and how. Drag it to move it, drag its edges to resize it. Arrow keys nudge it, Delete removes it.</p>
						{/if}
					</section>
				</aside>
			</div>
		{/if}
	</div>
</dialog>
