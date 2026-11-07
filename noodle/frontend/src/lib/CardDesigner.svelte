<script lang="ts">
	import Icon from './Icon.svelte';
	import { iconFor, isOn } from './api.ts';
	import CardBody from './devices/CardBody.svelte';
	import TileSubtitle from './devices/TileSubtitle.svelte';
	import {
		COLORS, COMPONENTS, HOURS, ICONS, MAX_H, MAX_W, PRESETS, STYLES, autoStyle, compatible, defaultDesign, freeSpot, grid, hoursLabel, minSize,
		placeable, presetFields, startSize, stylesFor, type CardColor, type CardDesign, type CardRule, type CardSlot, type CardStyle
	} from './devices/cardDesign.ts';
	import { TOKENS, resolve } from './devices/cardText.ts';
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
	const styles = $derived<CardStyle[]>(entity ? stylesFor(entity) : sel?.component === 'text' ? ['text-s', 'text-m', 'text-l', 'chip'] : []);
	let tab = $state<'content' | 'format' | 'rules'>('content');
	/** the rule that applies to the selected component right now (it is highlighted in the Rules list) */
	const matched = $derived(sel && device ? resolve(sel, device, Date.now()).rule : -1);
	const cardPx = $derived({ w: draft.w * CELL_W + (draft.w - 1) * GAP, h: draft.h * CELL_H + (draft.h - 1) * GAP });
	const fieldName = (k: string) => device?.entities.find((e) => e.key === k)?.name ?? k;

	// --- adding, changing, removing ---
	function add(p: (typeof PRESETS)[number]) {
		if (!device) return;
		const choices = presetFields(device, p);
		if (!choices.length && p.component !== 'text') return;
		const used = new Set(draft.slots.map((s) => s.key));
		const e = choices.find((c) => !used.has(c.key)) ?? choices[0];
		const want = startSize(p.component, p.style);
		// the size it likes, else the biggest that still fits somewhere
		for (let w = want.w; w >= 1; w--) {
			for (let h = want.h; h >= 1; h--) {
				const at = freeSpot(draft, w, h);
				if (!at) continue;
				draft.slots.push({ ...at, w, h, component: p.component, key: e?.key ?? '', ...(p.style ? { style: p.style } : {}) });
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
	function insert(token: string) {
		if (token && sel) patch({ template: (sel.template ?? '') + token });
	}
	function setRule(i: number, p: Partial<CardRule>) {
		if (sel) patch({ rules: (sel.rules ?? []).map((r, j) => (j === i ? { ...r, ...p } : r)) });
	}
	function setThen(i: number, p: Partial<CardRule['then']>) {
		if (sel) patch({ rules: (sel.rules ?? []).map((r, j) => (j === i ? { ...r, then: { ...r.then, ...p } } : r)) });
	}
	/** a starting comparison for a field: yes/no, a number, or text */
	function firstRule(key: string): Pick<CardRule, 'op' | 'value' | 'value2'> {
		const state = device?.entities.find((f) => f.key === key)?.state;
		return typeof state === 'boolean' ? { op: 'is', value: 'on' } : typeof state === 'number' ? { op: 'above', value: 0 } : { op: 'is', value: '' };
	}
	const resetValue = (key: string) => ({ ...firstRule(key), value2: undefined });
	function addRule() {
		if (sel) patch({ rules: [...(sel.rules ?? []), { ...firstRule(sel.key), then: { color: 'success' } }] });
	}
	function removeRule(i: number) {
		if (sel) patch({ rules: (sel.rules ?? []).filter((_, j) => j !== i) });
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
								<button class="btn btn-sm btn-soft" disabled={p.component !== 'text' && !presetFields(device, p).length} onclick={() => add(p)}>{p.label}</button>
							{/each}
						</div>
						<p class="min-h-8 text-xs opacity-70" role="status">{note}</p>
					</section>

<section class="flex min-h-72 flex-col gap-3">
						<h3 class="text-sm font-semibold">{sel ? (sel.component === 'value' ? 'Reading' : COMPONENTS[sel.component].label) : 'Selected'}</h3>
						{#if sel && (entity || sel.component === 'text')}
							<div class="tabs tabs-box tabs-sm" role="tablist">
								{#each [['content', 'Content'], ['format', 'Format'], ['rules', `Rules${sel.rules?.length ? ` (${sel.rules.length})` : ''}`]] as [id, label] (id)}
									<button role="tab" class="tab" class:tab-active={tab === id} onclick={() => (tab = id as typeof tab)}>{label}</button>
								{/each}
							</div>

							{#if tab === 'content'}
								{#if sel.component !== 'text'}
									<label class="flex flex-col gap-1 text-xs font-medium opacity-80">Shows
										<select class="select select-sm w-full" value={sel.key} onchange={(e) => setField(e.currentTarget.value)}>
											{#each fields as f (f.key)}<option value={f.key}>{f.name}</option>{/each}
										</select>
									</label>
								{/if}
								{#if sel.component === 'value' || sel.component === 'text'}
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
									<div class="flex flex-col gap-1 text-xs font-medium opacity-80">Text
										<input class="input input-sm w-full" value={sel.template ?? ''} placeholder={sel.component === 'text' ? 'Type your text' : 'As the device says it'} maxlength="200"
											oninput={(e) => patch({ template: e.currentTarget.value || undefined })} />
										<select class="select select-xs w-full" value="" onchange={(e) => { insert(e.currentTarget.value); e.currentTarget.value = ''; }} aria-label="Insert a value into the text">
											<option value="">Insert a value…</option>
											{#each TOKENS as t (t.token)}<option value={t.token}>{t.label}</option>{/each}
											{#each device.entities as f (f.key)}<option value={`{field:${f.key}}`}>{f.name} (field)</option>{/each}
										</select>
									</div>
								{/if}
								<label class="flex flex-col gap-1 text-xs font-medium opacity-80">Name on the card
									<input class="input input-sm w-full" value={sel.label ?? ''} placeholder={entity?.name ?? ''} maxlength="40" oninput={(e) => setLabel(e.currentTarget.value)} />
								</label>
							{:else if tab === 'format'}
								{#if entity && typeof entity.state === 'number'}
									<div class="flex flex-col gap-2 text-xs font-medium opacity-80">Number
										<div class="grid grid-cols-2 gap-2">
											<select class="select select-sm w-full" value={sel.decimals ?? ''} aria-label="Decimals" onchange={(e) => patch({ decimals: e.currentTarget.value === '' ? undefined : Number(e.currentTarget.value) })}>
												<option value="">Decimals: auto</option>
												{#each [0, 1, 2, 3, 4] as d (d)}<option value={d}>{d} decimals</option>{/each}
											</select>
											<input class="input input-sm w-full" value={sel.unit ?? ''} placeholder={entity.unit ? `Unit: ${entity.unit}` : 'Unit'} maxlength="10" aria-label="Unit"
												oninput={(e) => patch({ unit: e.currentTarget.value === '' ? undefined : e.currentTarget.value })} />
										</div>
										<label class="flex items-center gap-2 font-normal"><input type="checkbox" class="checkbox checkbox-sm" checked={!!sel.thousands} onchange={(e) => patch({ thousands: e.currentTarget.checked || undefined })} />Thousands separator</label>
									</div>
								{/if}
								<div class="flex flex-col gap-2 text-xs font-medium opacity-80">Text
									<div class="flex flex-wrap items-center gap-2">
										<button class="btn btn-xs" class:btn-primary={sel.bold} aria-pressed={!!sel.bold} onclick={() => patch({ bold: sel.bold ? undefined : true })}><b>B</b></button>
										<div class="join">
											{#each ['left', 'center', 'right'] as a (a)}
												<button class="btn btn-xs join-item" class:btn-primary={(sel.align ?? 'left') === a} onclick={() => patch({ align: a === 'left' ? undefined : (a as 'center' | 'right') })}>{a}</button>
											{/each}
										</div>
									</div>
									<div class="flex flex-wrap items-center gap-1.5" role="group" aria-label="Colour">
										<button class="btn btn-xs btn-circle btn-outline" class:btn-active={!sel.color} aria-label="No colour" onclick={() => patch({ color: undefined })}><Icon name="close" class="size-3" /></button>
										{#each Object.keys(COLORS) as c (c)}
											<button class="size-6 rounded-full border-2 {COLORS[c as CardColor].dot} {sel.color === c ? 'border-base-content' : 'border-transparent'}" aria-label={c} aria-pressed={sel.color === c} onclick={() => patch({ color: c as CardColor })}></button>
										{/each}
									</div>
								</div>
							{:else}
								<p class="text-xs opacity-70">First rule that is true wins. It can change the text, colour and icon, or hide the component.</p>
								{#each sel.rules ?? [] as r, i (i)}
									{@const target = device.entities.find((f) => f.key === (r.field || sel.key))}
									{@const kind = typeof target?.state === 'boolean' ? 'bool' : typeof target?.state === 'number' ? 'num' : 'text'}
									<div class="bg-base-200 rounded-box flex flex-col gap-2 p-2.5 {matched === i ? 'ring-primary ring-1' : ''}">
										<div class="flex items-center gap-1.5 text-xs">
											<span class="font-semibold">When</span>
											<select class="select select-xs min-w-0 grow" value={r.field ?? ''} aria-label="Field" onchange={(e) => setRule(i, { field: e.currentTarget.value || undefined, ...resetValue(e.currentTarget.value || sel.key) })}>
												{#if sel.key}<option value="">{entity?.name ?? 'this field'}</option>{/if}
												{#each device.entities.filter((f) => f.key !== sel.key) as f (f.key)}<option value={f.key}>{f.name}</option>{/each}
											</select>
											<button class="btn btn-ghost btn-xs btn-square" aria-label="Remove rule" onclick={() => removeRule(i)}><Icon name="close" class="size-3.5" /></button>
										</div>
										<div class="flex items-center gap-1.5">
											<select class="select select-xs w-24 shrink-0" value={r.op} aria-label="Comparison" onchange={(e) => setRule(i, { op: e.currentTarget.value as CardRule['op'] })}>
												<option value="is">is</option>
												<option value="not">is not</option>
												{#if kind === 'num'}<option value="above">above</option><option value="below">below</option><option value="between">between</option>{/if}
											</select>
											{#if kind === 'bool'}
												<select class="select select-xs min-w-0 grow" value={String(r.value)} aria-label="Value" onchange={(e) => setRule(i, { value: e.currentTarget.value })}>
													<option value="on">On / yes</option><option value="off">Off / no</option>
												</select>
											{:else if kind === 'num'}
												<input type="number" class="input input-xs min-w-0 grow" value={r.value} aria-label="Value" oninput={(e) => setRule(i, { value: Number(e.currentTarget.value) })} />
												{#if r.op === 'between'}<span class="text-xs">and</span>
													<input type="number" class="input input-xs min-w-0 grow" value={r.value2 ?? 0} aria-label="Upper value" oninput={(e) => setRule(i, { value2: Number(e.currentTarget.value) })} />{/if}
											{:else}
												<input class="input input-xs min-w-0 grow" value={r.value} aria-label="Value" maxlength="100" oninput={(e) => setRule(i, { value: e.currentTarget.value })} />
											{/if}
										</div>
										<span class="text-xs font-semibold">Then</span>
										<input class="input input-xs w-full" value={r.then.text ?? ''} placeholder="Show this text (optional)" maxlength="200" aria-label="Text"
											oninput={(e) => setThen(i, { text: e.currentTarget.value === '' ? undefined : e.currentTarget.value })} />
										<div class="flex items-center gap-1.5">
											<select class="select select-xs min-w-0 grow" value={r.then.color ?? ''} aria-label="Colour" onchange={(e) => setThen(i, { color: (e.currentTarget.value || undefined) as CardColor | undefined })}>
												<option value="">Colour: as is</option>
												{#each Object.keys(COLORS) as c (c)}<option value={c}>{c}</option>{/each}
											</select>
											<select class="select select-xs min-w-0 grow" value={r.then.icon ?? ''} aria-label="Icon" onchange={(e) => setThen(i, { icon: e.currentTarget.value || undefined })}>
												<option value="">Icon: as is</option>
												{#each ICONS as ic (ic)}<option value={ic}>{ic}</option>{/each}
											</select>
										</div>
										<label class="flex items-center gap-2 text-xs"><input type="checkbox" class="checkbox checkbox-xs" checked={!!r.then.hide} onchange={(e) => setThen(i, { hide: e.currentTarget.checked || undefined })} />Hide the component</label>
									</div>
								{/each}
								{#if (sel.rules?.length ?? 0) < 8}
									<button class="btn btn-sm btn-soft" onclick={addRule}><Icon name="plus" class="size-4" />Add a rule</button>
								{/if}
							{/if}
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
