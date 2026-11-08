<script lang="ts">
	import Icon from './Icon.svelte';
	import { iconFor, isOn, type Entity } from './api.ts';
	import CardBody from './devices/CardBody.svelte';
	import LookPreview from './devices/LookPreview.svelte';
	import TileSubtitle from './devices/TileSubtitle.svelte';
	import {
		COLORS, COMPONENTS, FONT_SIZES, HOURS, ICONS, MAX_H, MAX_W, PRESETS, STYLES, autoStyle, compatible, defaultDesign, freeSpot, grid, hoursLabel, isTextStyle, minSize,
		placeable, presetFields, presetSource, startSize, stylesFor, type CardColor, type CardDesign, type CardSlot, type CardStyle
	} from './devices/cardDesign.ts';
	import RulesEditor from './devices/RulesEditor.svelte';
	import { parseRules } from './devices/rules.ts';
	import { TOKENS, defaultTemplate, fieldsOf, fieldName as refName, fieldToken, otherRef, resolve, rulesToTemplate } from './devices/cardText.ts';
	import { deviceKind, kindName, motionActive } from './devices/kinds.ts';
	import { cardDesigner } from './designer.svelte';
	import { layout } from './layout.svelte';
	import { live } from './live.svelte';

	// The card is drawn at its real size on a stage that shows the dashboard's cells. These are the sizes of a cell
	// there (16rem x 9rem with 0.75rem between), in px; the stage shrinks to fit a small window.
	const CELL_W = 256, CELL_H = 144, GAP = 12, BODY_GAP = 6;

	// the side panel's width: drag the bar between the card and the panel (kept for next time)
	const PANEL_MIN = 280, PANEL_MAX = 720;
	const clampPanel = (w: number) => Math.min(PANEL_MAX, Math.max(PANEL_MIN, Math.round(w)));
	let panelW = $state(clampPanel((() => { try { return Number(localStorage.getItem('noodle.designer.panel')) || 360; } catch { return 360; } })()));
	function setPanel(w: number) {
		panelW = clampPanel(w);
		try { localStorage.setItem('noodle.designer.panel', String(panelW)); } catch { /* not kept */ }
	}
	function dragPanel(e: PointerEvent) {
		const bar = e.currentTarget as HTMLElement, x0 = e.clientX, w0 = panelW;
		bar.setPointerCapture(e.pointerId);
		const move = (m: PointerEvent) => (panelW = clampPanel(w0 + x0 - m.clientX));
		const up = () => { bar.removeEventListener('pointermove', move); bar.removeEventListener('pointerup', up); setPanel(panelW); };
		bar.addEventListener('pointermove', move);
		bar.addEventListener('pointerup', up);
	}

	let loadedFor: string | null = null;
	const device = $derived(cardDesigner.deviceId ? live.devices[cardDesigner.deviceId] : undefined);
	let draft = $state<CardDesign>({ w: 1, h: 1, slots: [] });
	let selected = $state<number | null>(null);
	let note = $state('');
	let bodyEl = $state<HTMLElement>();
	let available = $state(800);
	let availableH = $state(600);
	const cardPx = $derived({ w: draft.w * CELL_W + (draft.w - 1) * GAP, h: draft.h * CELL_H + (draft.h - 1) * GAP });
	// The stage shows only the card, as big as fits, with room beside it for the + buttons.
	const BTN = 52;
	const scale = $derived(Math.max(0.4, Math.min(1.8, (available - 48 - BTN) / cardPx.w, (availableH - 48 - BTN) / cardPx.h)));

	$effect(() => {
		if (device && loadedFor !== device.id) {
			loadedFor = device.id;
			// Open on what the card looks like now: the saved design, else the device's own look written as a design.
			const start = layout.designFor(device) ?? defaultDesign(device);
			draft = start
				? { w: start.w, h: start.h, slots: start.slots.map((s) => ({ ...s, ...(s.component === 'value' ? { style: s.style ?? autoStyle(device.entities.find((e) => e.key === s.key)) } : {}) })) }
				: { w: 1, h: 1, slots: [] };
			selected = null;
			note = '';
		}
		if (!device) loadedFor = null;
	});

	const sel = $derived(selected !== null ? draft.slots[selected] : undefined);
	/** a switch and a knob show no text, so bold, size and alignment mean nothing to them */
	const showsText = $derived(!!sel && sel.component !== 'switch' && sel.component !== 'knob');
	/** the device the selected reading takes its field from: another one if chosen, else this one */
	const source = $derived(sel?.component === 'value' && sel.device ? (live.devices[sel.device] ?? device) : device);
	const entity = $derived(sel && source ? fieldsOf(source).find((e) => e.key === sel.key) : undefined);
	const fields = $derived(sel && source ? fieldsOf(source).filter((e) => compatible(sel.component, e)) : []);
	/** every device, for a reading to pick from */
	const allDevices = $derived(Object.values(live.devices).sort((a, b) => a.name.localeCompare(b.name)));
	function setSource(id: string) {
		if (selected === null || !sel || !device) return;
		const d = id && id !== device.id ? live.devices[id] : device;
		if (!d) return;
		const style = sel.style ?? 'text-l';
		const pick = fieldsOf(d).find((e) => compatible('value', e) && stylesFor(e).includes(style)) ?? fieldsOf(d).find((e) => compatible('value', e));
		if (!pick) { note = `${d.name} has no field to show.`; return; }
		const next: CardSlot = { ...sel, key: pick.key };
		if (d.id === device.id) delete next.device; else next.device = d.id;
		if (!stylesFor(pick).includes(style)) next.style = stylesFor(pick)[0];
		draft.slots[selected] = next;
		note = '';
	}
	/** a graph takes its data from what the text says, so it needs no field, device or span to pick */
	const graphStyle = $derived(sel?.component === 'value' && !!sel.style && STYLES[sel.style].graph);
	/** the component's text is written in the editor, so it needs no "Shows" field and no caption */
	const written = $derived(sel?.component === 'text' || (sel?.component === 'value' && (isTextStyle(sel.style) || sel.style === 'chip')));
	/** what has something that fills or draws: a slider, bar, gauge, graph, status bar, the power button */
	const hasFill = $derived(!!sel && !written && sel.component !== 'button' && sel.component !== 'knob' || sel?.style === 'chip');
	let area = $state<HTMLTextAreaElement>();
	/** a mistake in the selected component's template */
	const templateError = $derived(sel?.template && device ? resolve(sel, device, 0).error : undefined);
	const fieldName = (k: string) => device?.entities.find((e) => e.key === k)?.name ?? k;

	// --- adding, changing, removing ---
	function add(p: (typeof PRESETS)[number]) {
		if (!device) return;
		const choices = presetFields(device, p);
		const from = choices.length ? undefined : presetSource(device, p, allDevices);
		if (!choices.length && !from && p.component !== 'text') return;
		const used = new Set(draft.slots.map((s) => s.key));
		const e = from?.entity ?? choices.find((c) => !used.has(c.key)) ?? choices[0];
		const want = startSize(p.component, p.style);
		// the size it likes, else the biggest that still fits somewhere
		for (let w = want.w; w >= 1; w--) {
			for (let h = want.h; h >= 1; h--) {
				const at = freeSpot(draft, w, h);
				if (!at) continue;
				draft.slots.push({ ...at, w, h, component: p.component, key: e?.key ?? '', ...(from?.device ? { device: from.device } : {}), ...(p.style ? { style: p.style } : {}) });
				selected = draft.slots.length - 1;
				note = '';
				return;
			}
		}
		note = 'No room left on the card. Make the card bigger or move things.';
	}
	/** turn the selected component into another kind (keeps its place, size and text) */
	function change(p: (typeof PRESETS)[number]) {
		if (selected === null || !sel || !device) return;
		const choices = presetFields(device, p);
		// a reading keeps the other device it already shows; else it may fall back to any device that has a fitting field
		const other = sel.component === 'value' && p.component === 'value' && sel.device && live.devices[sel.device] ? presetFields(live.devices[sel.device], p) : [];
		const from = choices.length || other.length ? undefined : presetSource(device, p, allDevices);
		if (!choices.length && !other.length && !from && p.component !== 'text') return;
		const keepFrom = other.length ? other : choices;
		const keep = from?.entity ?? keepFrom.find((c) => c.key === sel.key) ?? keepFrom[0];
		const next: CardSlot = { ...sel, component: p.component, key: p.component === 'text' ? '' : keep.key };
		if (p.component === 'value' && (other.length || from?.device)) next.device = from?.device ?? sel.device;
		else delete next.device;
		if (p.style) next.style = p.style;
		else delete next.style;
		if (p.style && STYLES[p.style].graph) next.hours = sel.hours ?? 6;
		else delete next.hours;
		draft.slots[selected] = next;
		note = '';
	}
	function setField(key: string) {
		if (selected === null || !sel) return;
		const e = source ? fieldsOf(source).find((x) => x.key === key) : undefined;
		const next: CardSlot = { ...sel, key };
		if (sel.component === 'value' && e && !stylesFor(e).includes(sel.style ?? 'text-l')) next.style = stylesFor(e)[0];
		draft.slots[selected] = next;
	}
	function patch(p: Partial<CardSlot>) {
		if (selected !== null && sel) draft.slots[selected] = { ...sel, ...p };
	}
	/** the text in the editor: what is written, else the field the component shows, written out so it is clear how it works */
	const tpl = $derived(sel?.template ?? (device && sel ? defaultTemplate(sel, device, source) : ''));
	// the text as rules ("when … then …") or as code; rules when the text has an if and the rules view can show it
	let view = $state<'rules' | 'text' | null>(null);
	$effect(() => { void selected; view = null; });
	const rulesOk = $derived(parseRules(tpl) !== null);
	const mode = $derived(view ?? (rulesOk && /\{if\b/.test(tpl) ? 'rules' : 'text'));

	const SPANS = ['1h', '5h', '12h', '24h', '3d', '7d'];
	// --- suggestions while typing a name (device.…, another device's name, value) ---
	let hints = $state<string[]>([]);
	let hintAt = $state(0);
	let hintFrom = 0;
	/** where the suggestions pop up: just under the word being typed (px inside the text box's wrapper) */
	let hintXY = $state({ x: 0, y: 0 });
	/** the caret's place in the text box, measured on a hidden copy of the text */
	function caretXY(el: HTMLTextAreaElement, at: number) {
		const cs = getComputedStyle(el);
		const mirror = document.createElement('div');
		for (const k of ['fontFamily', 'fontSize', 'fontWeight', 'lineHeight', 'letterSpacing', 'paddingTop', 'paddingLeft', 'paddingRight', 'paddingBottom', 'borderLeftWidth', 'borderTopWidth', 'boxSizing', 'tabSize'] as const) mirror.style[k] = cs[k];
		Object.assign(mirror.style, { position: 'absolute', visibility: 'hidden', whiteSpace: 'pre-wrap', overflowWrap: 'break-word', width: `${el.offsetWidth}px`, top: '0', left: '0' });
		mirror.textContent = el.value.slice(0, at);
		const mark = document.createElement('span');
		mark.textContent = '\u200b';
		mirror.append(mark);
		el.parentElement!.append(mirror);
		const out = { x: mark.offsetLeft - el.scrollLeft, y: mark.offsetTop - el.scrollTop + (parseFloat(cs.lineHeight) || 20) };
		mirror.remove();
		return out;
	}
	function candidates(): string[] {
		if (!device) return [];
		const own = fieldsOf(device!).map((f) => refName(device!, f));
		const others = live.list.filter((d) => d.id !== device!.id).flatMap((d) => d.entities.map((f) => otherRef(d, f)));
		// a number can be graphed: device.brightness.history, with how far back to go
		const hist = (d: typeof device, ref: (f: Entity) => string) => fieldsOf(d!).filter((f) => typeof f.state === 'number').flatMap((f) => [`${ref(f)}.history`, ...SPANS.map((s) => `${ref(f)}.history.${s}`)]);
		return ['value', 'name', 'unit', 'device.name', ...own, ...hist(device, (f) => refName(device!, f)), ...others, ...live.list.filter((d) => d.id !== device!.id).flatMap((d) => hist(d, (f) => otherRef(d, f)))];
	}
	function refreshHints() {
		const el = area;
		if (!el || !device) return (hints = []);
		const at = el.selectionStart ?? 0, before = el.value.slice(0, at);
		const m = /[A-Za-z0-9_.]+$/.exec(before);
		const open = before.lastIndexOf('{') > before.lastIndexOf('}');
		if (!m || !open || (m[0].length < 2 && !m[0].endsWith('.'))) return (hints = []);
		const t = m[0].toLowerCase();
		const all = candidates();
		const found = [...all.filter((c) => c.toLowerCase().startsWith(t)), ...all.filter((c) => !c.toLowerCase().startsWith(t) && c.toLowerCase().includes(t))].filter((c) => c.toLowerCase() !== t);
		hints = [...new Set(found)].slice(0, 8);
		hintAt = 0;
		hintFrom = at - m[0].length;
		hintXY = caretXY(el, hintFrom);
	}
	function accept(h: string) {
		const el = area;
		if (!el || !sel) return;
		const at = el.selectionStart ?? 0;
		const closes = el.value[hintFrom - 1] === '{' && el.value[at] !== '}';
		const text = el.value.slice(0, hintFrom) + h + (closes ? '}' : '') + el.value.slice(at);
		patch({ template: text.slice(0, 1000) });
		hints = [];
		const to = hintFrom + h.length + (closes ? 1 : 0);
		queueMicrotask(() => { el.focus(); el.setSelectionRange(to, to); });
	}
	function hintKey(e: KeyboardEvent) {
		if (!hints.length) return;
		if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); hintAt = (hintAt + (e.key === 'ArrowDown' ? 1 : hints.length - 1)) % hints.length; }
		else if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); accept(hints[hintAt]); }
		else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); hints = []; }
	}

	/** put text into the template where the cursor is (at the end when there is no cursor) */
	function insert(snippet: string) {
		if (!snippet || !sel) return;
		const text = tpl;
		const from = area?.selectionStart ?? text.length, to = area?.selectionEnd ?? text.length;
		patch({ template: (text.slice(0, from) + snippet + text.slice(to)).slice(0, 1000) });
		const at = from + snippet.length;
		queueMicrotask(() => { area?.focus(); area?.setSelectionRange(at, at); });
	}
	/** put the selected text of the box between two tags (nothing selected: an empty pair, the cursor inside) */
	function wrap(open: string, close: string) {
		if (!sel) return;
		const text = tpl;
		const from = area?.selectionStart ?? text.length, to = area?.selectionEnd ?? text.length;
		patch({ template: (text.slice(0, from) + open + text.slice(from, to) + close + text.slice(to)).slice(0, 1000) });
		const at = from + open.length, end = to + open.length;
		queueMicrotask(() => { area?.focus(); area?.setSelectionRange(at, end); });
	}
	/** like wrap, but with nothing selected it covers the whole text (a size or style for the component) */
	function wrapOrAll(open: string, close: string) {
		if (!sel) return;
		if ((area?.selectionStart ?? 0) === (area?.selectionEnd ?? 0)) area?.setSelectionRange(0, tpl.length);
		wrap(open, close);
	}
	/** the component's background colour: {bg colour} goes in the text where the cursor is; no colour takes them all out */
	function setBg(c?: string) {
		if (!sel) return;
		if (c) return insert(`{bg ${c}}`);
		const t = tpl.replace(/\{bg [^{}]*\}\r?\n?/g, '');
		patch({ template: t || undefined });
	}
	/** the colour of what fills or draws (slider, bar, gauge, graph, power button): {fill colour} goes in where the cursor is */
	function setFill(c?: string) {
		if (!sel) return;
		if (c) return insert(`{fill ${c}}`);
		const t = tpl.replace(/\{fill [^{}]*\}\r?\n?/g, '');
		patch({ template: t || undefined });
	}
	/** take a colour off the selected text: its {color …} and {/color} go */
	function unwrapColor() {
		if (!tpl) return;
		const from = area?.selectionStart ?? 0, to = area?.selectionEnd ?? tpl.length;
		const t = tpl;
		const mid = t.slice(from, to).replace(/\{color [^{}]*\}|\{\/color\}/g, '');
		patch({ template: t.slice(0, from) + mid + t.slice(to) });
	}
	function condFor(key: string): string {
		const f = device?.entities.find((x) => x.key === key);
		const name = f && device ? refName(device, f) : key;
		return typeof f?.state === 'boolean' ? `${name} == true` : typeof f?.state === 'number' ? `${name} > 0` : `${name} == 'text'`;
	}
	function ifBlock(key: string): string {
		return `{if ${condFor(key)}}
Yes
{:else}
No
{/if}`;
	}
	function convertRules() {
		if (sel && device) patch({ template: rulesToTemplate(sel, device).slice(0, 1000), rules: undefined });
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
	}
		function key(e: KeyboardEvent) {
		if (e.key === 'Escape' && device && !e.defaultPrevented) return cardDesigner.close();
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
	const kind = $derived(device ? deviceKind(device) : 'generic');
	/** this design for every device of the kind; this device then follows it */
	function applyToKind() {
		if (!device || !draft.slots.length) return;
		// devices of this kind that were designed on their own: "apply to all" replaces those too
		const own = live.list.filter((d) => deviceKind(d) === kind && layout.cards[d.id]);
		if (own.length && !confirm(`${own.length} ${own.length === 1 ? 'device has' : 'devices have'} a card design of ${own.length === 1 ? 'its' : 'their'} own (${own.map((d) => d.name).join(', ')}). Replace ${own.length === 1 ? 'it' : 'them'} with this one?`)) return;
		layout.setKindDefault(kind, $state.snapshot(draft));
		for (const d of own) layout.setCard(d.id, null);
		layout.setCard(device.id, null);
		cardDesigner.close();
	}
	function removeKindDefault() {
		layout.setKindDefault(kind, null);
		cardDesigner.close();
	}
	function reset() {
		if (!device) return;
		layout.setCard(device.id, null);
		cardDesigner.close();
	}
</script>

<svelte:window onkeydown={key} />

{#if device}
	<!-- Laid out like the automation editor: the whole screen next to the side menu, a bar on top (back at the left, Save at the right), the panels as rounded boxes. -->
	<div class="bg-base-200 fixed inset-0 z-40 flex flex-col gap-2 p-2 lg:left-60" role="dialog" aria-label="Design the card of {device.name}">
		<div class="bg-base-100 border-base-content/10 rounded-box relative z-30 flex items-center gap-1 border px-2 py-1">
			<button class="btn btn-ghost btn-sm btn-square" aria-label="Back without saving" title="Back without saving (Esc)" onclick={() => cardDesigner.close()}><Icon name="left" class="size-4" /></button>
			<h2 class="min-w-0 grow truncate px-2 font-bold">Card of {device.name}</h2>
			{#if layout.cards[device.id]}<button class="btn btn-ghost btn-sm" onclick={reset}>Back to the default look</button>{/if}
			{#if layout.cardDefaults[kind]}<button class="btn btn-ghost btn-sm" title="Every {kindName(kind)} goes back to the built-in look (unless it has its own design)" onclick={removeKindDefault}>Remove the default for {kindName(kind)}</button>{/if}
			<button class="btn btn-sm btn-outline" disabled={!draft.slots.length} title="Every {kindName(kind)} gets this card, also the ones you designed on their own (you are asked first)" onclick={applyToKind}>Apply to all {kindName(kind)}</button>
			<button class="btn btn-sm btn-primary" onclick={save}>Save</button>
		</div>

		<div class="flex min-h-0 grow flex-col gap-3 lg:flex-row">
				<!-- The stage: the card exactly as it will look, with + buttons to make it bigger. -->
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<div class="bg-base-100 border-base-content/10 rounded-box min-h-0 min-w-0 grow overflow-auto border p-6" bind:clientWidth={available} bind:clientHeight={availableH}
					onpointerdown={(e) => { if (!(e.target as HTMLElement).closest('[data-slot], button')) selected = null; }}>
					<div class="relative" style="width: {cardPx.w * scale + BTN}px; height: {cardPx.h * scale + BTN}px;">
					<div class="absolute top-0 left-0 origin-top-left" style="width: {cardPx.w}px; height: {cardPx.h}px; transform: scale({scale});">
						<div class="tile absolute top-0 left-0 flex flex-col justify-between gap-3 p-3.5" class:is-on={isOn(device) || motionActive(device)}
								style="width: {cardPx.w}px; height: {cardPx.h}px; transform: none">
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
								</div>
						</div>
					<!-- grow or shrink the card: + and − beside it -->
					<div class="absolute flex flex-col justify-center gap-1" style="left: {cardPx.w * scale + 8}px; top: 0; height: {cardPx.h * scale}px;">
						<button class="btn btn-sm btn-square btn-soft" aria-label="Wider" title="Wider" disabled={draft.w >= MAX_W} onclick={() => setSize(draft.w + 1, draft.h)}>+</button>
						<button class="btn btn-sm btn-square btn-ghost" aria-label="Narrower" title="Narrower" disabled={draft.w <= minSize(draft).w} onclick={() => setSize(draft.w - 1, draft.h)}>−</button>
					</div>
					<div class="absolute flex justify-center gap-1" style="top: {cardPx.h * scale + 8}px; left: 0; width: {cardPx.w * scale}px;">
						<button class="btn btn-sm btn-square btn-soft" aria-label="Taller" title="Taller" disabled={draft.h >= MAX_H} onclick={() => setSize(draft.w, draft.h + 1)}>+</button>
						<button class="btn btn-sm btn-square btn-ghost" aria-label="Shorter" title="Shorter" disabled={draft.h <= minSize(draft).h} onclick={() => setSize(draft.w, draft.h - 1)}>−</button>
					</div>
					<button class="btn btn-sm btn-square btn-soft absolute" style="left: {cardPx.w * scale + 8}px; top: {cardPx.h * scale + 8}px;" aria-label="Wider and taller" title="Wider and taller" disabled={draft.w >= MAX_W && draft.h >= MAX_H} onclick={() => setSize(draft.w + 1, draft.h + 1)}>+</button>
				</div>
			</div>

			<div class="hover:bg-primary/40 active:bg-primary/60 -mx-2 hidden w-1.5 shrink-0 cursor-col-resize touch-none transition-colors lg:block" role="slider" aria-orientation="vertical" aria-valuemin={PANEL_MIN} aria-valuemax={PANEL_MAX} aria-valuenow={panelW}
						aria-label="Panel width" tabindex="0" onpointerdown={dragPanel}
						onkeydown={(e) => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); setPanel(panelW + (e.key === 'ArrowLeft' ? 24 : -24)); } }}></div>

<!-- The panel never changes place: what is selected only fills it in. -->
				<aside class="bg-base-100 border-base-content/10 rounded-box flex max-h-[45dvh] shrink-0 flex-col gap-5 overflow-y-auto border p-4 lg:max-h-none lg:w-[var(--pw)]" style="--pw: {panelW}px">
					<details class="group" open>
						<summary class="cursor-pointer text-sm font-semibold select-none">{sel ? 'Change this to' : 'Add to the card'}</summary>
						<div class="mt-2 grid grid-cols-3 gap-2">
							{#each PRESETS as p (p.id)}
								<button class="btn btn-soft h-auto flex-col gap-0.5 px-1 py-2 text-xs" disabled={p.component !== 'text' && !presetSource(device, p, allDevices)} title={p.component !== 'text' && !presetSource(device, p, allDevices) ? `${p.label} needs a ${STYLES[p.style ?? 'text-m']?.numeric ? 'number field' : 'matching field'} and no device has one` : undefined} onclick={() => (sel ? change(p) : add(p))}>
										<LookPreview look={p.component === 'text' ? 'label' : (p.style ?? p.component)} class="h-8 w-full" />{p.label}</button>
							{/each}
						</div>
						{#if sel}<button class="btn btn-ghost btn-xs mt-1" onclick={() => (selected = null)}>Add a new one instead</button>{/if}
						<p class="min-h-8 text-xs opacity-70" role="status">{note}</p>
					</details>

<section class="flex min-h-72 flex-col gap-3">
						<h3 class="text-sm font-semibold">{sel ? (sel.component === 'value' ? 'Reading' : COMPONENTS[sel.component].label) : 'Selected'}</h3>
						{#if sel && (entity || sel.component === 'text')}
							{#if sel.component === 'value' && !isTextStyle(sel.style) && !graphStyle}
								<label class="flex flex-col gap-1 text-xs font-medium opacity-80">From device
									<select class="select select-sm w-full" value={sel.device ?? device.id} onchange={(e) => setSource(e.currentTarget.value)}>
										{#each allDevices as d (d.id)}<option value={d.id}>{d.name}{d.id === device.id ? ' (this device)' : ''}</option>{/each}
									</select>
								</label>
							{/if}
							{#if !written && !graphStyle}
								<label class="flex flex-col gap-1 text-xs font-medium opacity-80">Shows
									<select class="select select-sm w-full" value={sel.key} onchange={(e) => setField(e.currentTarget.value)}>
										{#each fields as f (f.key)}<option value={f.key}>{f.name}</option>{/each}
									</select>
								</label>
							{/if}
							{#if sel.component === 'button'}
								{#if (entity?.actions?.length ?? 0) > 1}
									<label class="flex flex-col gap-1 text-xs font-medium opacity-80">Press
										<select class="select select-sm w-full" value={sel.action ?? ''} onchange={(e) => patch({ action: e.currentTarget.value || undefined })}>
											<option value="">The button's own press</option>
											{#each entity!.actions!.filter((a) => !/release|hold/.test(a)) as a (a)}<option value={a}>{a.replaceAll('_', ' ')}</option>{/each}
										</select>
									</label>
								{/if}
								<label class="flex flex-col gap-1 text-xs font-medium opacity-80">Text on the button
									<input class="input input-sm w-full" value={sel.label ?? ''} maxlength="40" placeholder="The button's name" onchange={(e) => patch({ label: e.currentTarget.value.trim() || undefined })} />
								</label>
							{/if}
							{#if sel}
																
								{#if graphStyle}
									<p class="bg-base-200 rounded-box p-2 text-xs opacity-80">The text draws the graph: <code>{'{device.brightness.history}'}</code> is the last 5 hours of this device's brightness. Add a span: <code>.1h</code> <code>.24h</code> <code>.7d</code>. Use another device's name for its data. Other text in the box shows on the graph.</p>
								{/if}

								<div class="tabs tabs-box tabs-sm self-start" role="tablist" aria-label="How to edit the text">
									<button class="tab" class:tab-active={mode === 'rules'} role="tab" aria-selected={mode === 'rules'} disabled={!rulesOk} title={rulesOk ? 'Change how it looks with rules' : 'This text has more in it than the rules view can show'} onclick={() => (view = 'rules')}>Rules</button>
									<button class="tab" class:tab-active={mode === 'text'} role="tab" aria-selected={mode === 'text'} onclick={() => (view = 'text')}>Text</button>
								</div>
								{#if mode === 'rules' && rulesOk}
									<RulesEditor template={tpl} {device} devices={allDevices} {entity} {hasFill} onchange={(t) => patch({ template: t.slice(0, 1000) || undefined })} />
									{#if templateError}<span class="text-error mt-1 text-xs" role="alert">{templateError}</span>{/if}
								{:else}
								<div class="flex flex-col text-xs font-medium opacity-80">Text
									<!-- the toolbar, like an editor's: insert things, and style the text -->
									<div class="bg-base-200 rounded-t-box border-base-content/15 mt-1 flex flex-wrap items-center gap-1.5 border border-b-0 p-1.5" role="toolbar" aria-label="Insert and style">
										<select class="select select-sm w-32" value="" onchange={(e) => { insert(e.currentTarget.value); e.currentTarget.value = ''; }} aria-label="Insert a value">
											<option value="">Insert value</option>
											<optgroup label="This component">{#each TOKENS as t (t.token)}<option value={t.token}>{t.label}</option>{/each}</optgroup>
											<optgroup label="Fields of the device">{#each fieldsOf(device) as f (f.key)}<option value={fieldToken(device, f)}>{f.name}</option>{/each}</optgroup>
											<optgroup label="Graph (last 5 hours)">{#each fieldsOf(device).filter((f) => typeof f.state === 'number') as f (f.key)}<option value={`{${refName(device, f)}.history}`}>{f.name} graph</option>{/each}</optgroup>
										</select>
										<select class="select select-sm w-32" value="" onchange={(e) => { const v = e.currentTarget.value; insert(v.startsWith('if:') ? ifBlock(v.slice(3)) : v); e.currentTarget.value = ''; }} aria-label="Insert a block">
											<option value="">Insert block</option>
											<optgroup label="If / else, on a field">{#each fieldsOf(device) as f (f.key)}<option value={`if:${f.key}`}>if {f.name}</option>{/each}</optgroup>
											<optgroup label="Style">
												<option value={'{color success}'}>text colour…</option><option value={'{fill success}'}>fill colour…</option><option value={'{icon motion}'}>icon…</option><option value={'{hide}'}>hide</option>
											</optgroup>
										</select>
{#if showsText}
										<span class="bg-base-content/15 mx-0.5 h-5 w-px"></span>
										<button class="btn btn-sm btn-square text-base" aria-label="Bold" title="Bold the selected text" onclick={() => wrap('{b}', '{/b}')}><b>B</b></button>
										<button class="btn btn-sm btn-square text-base" aria-label="Italic" title="Italic the selected text" onclick={() => wrap('{i}', '{/i}')}><i>I</i></button>
										<button class="btn btn-sm btn-square text-base" aria-label="Underline" title="Underline the selected text" onclick={() => wrap('{u}', '{/u}')}><u>U</u></button>
										<span class="bg-base-content/15 mx-0.5 h-5 w-px"></span>
										<div class="join">
											{#each [['left', 'M2 3h12M2 7h8M2 11h12'], ['center', 'M2 3h12M4 7h8M2 11h12'], ['right', 'M2 3h12M6 7h8M2 11h12']] as [a, path] (a)}
												<button class="btn btn-sm join-item btn-square" class:btn-primary={(sel.align ?? 'left') === a} aria-pressed={(sel.align ?? 'left') === a} aria-label="Align {a}" title="Align {a}"
													onclick={() => patch({ align: a === 'left' ? undefined : (a as 'center' | 'right') })}>
													<svg viewBox="0 0 16 14" class="size-5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d={path} /></svg></button>
											{/each}
										</div>
										<details class="dropdown">
											<summary class="btn btn-sm gap-1 px-2" aria-label="Text colour" title="Text colour">
												<span class="text-base font-bold underline decoration-primary decoration-2">A</span><span class="text-[10px]">▾</span></summary>
											<div class="dropdown-content bg-base-100 rounded-box z-10 mt-1 flex w-44 flex-wrap gap-1.5 p-2 shadow-lg" role="group" aria-label="Colour">
												<button class="btn btn-xs btn-circle btn-outline" aria-label="No colour" title="Remove colour from the selected text" onclick={(e) => { unwrapColor(); e.currentTarget.closest('details')?.removeAttribute('open'); }}><Icon name="close" class="size-3" /></button>
												{#each Object.keys(COLORS) as c (c)}
													<button class="size-6 rounded-full border-2 {COLORS[c as CardColor].dot} border-transparent" aria-label={c} title="Colour the selected text {c}"
														onclick={(e) => { wrap(`{color ${c}}`, '{/color}'); e.currentTarget.closest('details')?.removeAttribute('open'); }}></button>
												{/each}
													<label class="flex items-center gap-1 text-xs font-normal" title="Any colour"><input type="color" class="h-6 w-8 cursor-pointer rounded" value="#3b82f6" aria-label="Pick any colour" onchange={(e) => { wrap(`{color ${e.currentTarget.value}}`, '{/color}'); e.currentTarget.closest('details')?.removeAttribute('open'); }} />Any colour</label>
											</div>
										</details>
									<span class="bg-base-content/15 mx-0.5 h-5 w-px"></span>
											<select class="select select-sm w-20" value="" onchange={(e) => { const n = e.currentTarget.value; if (n) wrapOrAll(`{size ${n}}`, '{/size}'); e.currentTarget.value = ''; }} aria-label="Font size" title="Font size of the selected text (all of it when nothing is selected)">
												<option value="">Size</option>
												{#each FONT_SIZES as n (n)}<option value={n}>{n}</option>{/each}
											</select>
{/if}
											<details class="dropdown">
												<summary class="btn btn-sm gap-1 px-2" aria-label="Background colour" title="Background colour of this component">
													<span class="text-xs">Background colour</span><span class="text-[10px]">▾</span></summary>
												<div class="dropdown-content bg-base-100 rounded-box z-10 mt-1 flex w-48 flex-col gap-1.5 p-2 shadow-lg" role="group" aria-label="Background colour">
													<span class="text-xs font-medium">Background of this component</span>
													<div class="flex flex-wrap gap-1.5">
														<button class="btn btn-xs btn-circle btn-outline" aria-label="No background colour" title="No background colour" onclick={(e) => { setBg(); e.currentTarget.closest('details')?.removeAttribute('open'); }}><Icon name="close" class="size-3" /></button>
														{#each Object.keys(COLORS) as c (c)}
															<button class="size-6 rounded-full border-2 {COLORS[c as CardColor].dot} border-transparent" aria-label={c} title="Background {c}" onclick={(e) => { setBg(c); e.currentTarget.closest('details')?.removeAttribute('open'); }}></button>
														{/each}
													<label class="flex items-center gap-1 text-xs font-normal" title="Any colour"><input type="color" class="h-6 w-8 cursor-pointer rounded" value="#3b82f6" aria-label="Pick any colour" onchange={(e) => { setBg(e.currentTarget.value); e.currentTarget.closest('details')?.removeAttribute('open'); }} />Any colour</label>
													</div>
													<span class="text-xs font-normal opacity-70">Goes in at the cursor. Put it inside an if block to change it with a field.</span>
												</div>
											</details>
{#if hasFill}
											<details class="dropdown">
												<summary class="btn btn-sm gap-1 px-2" aria-label="Fill colour" title="Fill colour">
													<span class="text-xs">Fill colour</span><span class="text-[10px]">▾</span></summary>
												<div class="dropdown-content bg-base-100 rounded-box z-10 mt-1 flex w-48 flex-col gap-1.5 p-2 shadow-lg" role="group" aria-label="Fill colour">
													<span class="text-xs font-medium">Fill of this component</span>
													<div class="flex flex-wrap gap-1.5">
														<button class="btn btn-xs btn-circle btn-outline" aria-label="No fill colour" title="No fill colour" onclick={(e) => { setFill(); e.currentTarget.closest('details')?.removeAttribute('open'); }}><Icon name="close" class="size-3" /></button>
														{#each Object.keys(COLORS) as c (c)}
															<button class="size-6 rounded-full border-2 {COLORS[c as CardColor].dot} border-transparent" aria-label={c} title="Fill {c}" onclick={(e) => { setFill(c); e.currentTarget.closest('details')?.removeAttribute('open'); }}></button>
														{/each}
													<label class="flex items-center gap-1 text-xs font-normal" title="Any colour"><input type="color" class="h-6 w-8 cursor-pointer rounded" value="#3b82f6" aria-label="Pick any colour" onchange={(e) => { setFill(e.currentTarget.value); e.currentTarget.closest('details')?.removeAttribute('open'); }} />Any colour</label>
													</div>
													<span class="text-xs font-normal opacity-70">The colour of a slider's or bar's fill, a gauge, a graph or the power button. Goes in at the cursor; put it inside an if block to change it with a field.</span>
												</div>
											</details>
{/if}
										</div>
									<div class="relative">
									<textarea bind:this={area} class="textarea rounded-t-none w-full font-mono text-sm leading-snug" rows="10" spellcheck="false" maxlength="1000"
										value={tpl} placeholder={sel.component === 'text' ? 'Type your text' : sel.component === 'value' ? 'Empty: the field as the device says it. Or write what to show, with {if …} blocks.' : 'Empty: as it is. Change it with a field, like {if device.brightness > 50}{bg success}{/if}, or write text to show on it.'}
										oninput={(e) => { patch({ template: e.currentTarget.value || undefined }); refreshHints(); }} onkeydown={hintKey} onkeyup={(e) => { if (!['ArrowDown', 'ArrowUp', 'Enter', 'Tab', 'Escape'].includes(e.key)) refreshHints(); }} onclick={refreshHints} onblur={() => setTimeout(() => (hints = []), 150)}></textarea>
										{#if hints.length}
											<div class="bg-base-100 border-primary/40 rounded-box absolute z-20 flex max-h-56 min-w-40 max-w-[90%] flex-col overflow-auto border-2 font-mono text-xs shadow-xl" style="left: {Math.max(0, hintXY.x)}px; top: {hintXY.y}px;" role="listbox" aria-label="Suggestions: Tab or Enter to pick, Esc to close">
												{#each hints as h, i (h)}
													<button class="px-2 py-1 text-left {i === hintAt ? 'bg-primary text-primary-content' : 'hover:bg-base-200'}" role="option" aria-selected={i === hintAt} onmousedown={(e) => { e.preventDefault(); accept(h); }}>{h}</button>
												{/each}
												<span class="bg-base-200 text-base-content/60 px-2 py-0.5 font-sans text-[10px]">↑↓ move · Tab or Enter picks · Esc closes</span>
											</div>
										{/if}
									</div>
									{#if templateError}<span class="text-error mt-1 font-normal" role="alert">{templateError}</span>{/if}
									<details class="mt-1 font-normal opacity-80">
										<summary class="cursor-pointer">How to write it</summary>
										<pre class="bg-base-200 rounded-box mt-1 p-2 text-[11px] leading-snug whitespace-pre-wrap">{`{if device.motion == true}
  {color success}Motion detected{/color}
{:else if device.temp > 25}
  Warm: {b}{device.temp}{/b}
{:else}
  {color error}No motion{/color}
{/if}`}</pre>
										<p class="mt-1">Values in braces: <code>{'{value}'}</code> (this component's field), <code>{'{device.name}'}</code> or any field of the device, like <code>{'{device.occupancy}'}</code>. Other devices work too: <code>{'{living_room_lamp.brightness}'}</code>, also in conditions. Start typing a name and pick from the suggestions. Conditions: == != &gt; &lt; &gt;= &lt;= and or not. Style words with <code>{'{color success}…{/color}'}</code> (primary, success, warning, error, info… or any CSS colour: <code>{'{bg #3b82f6}'}</code>, <code>{'{fill rgba(0, 0, 0, 0.3)}'}</code>, hsl()…), <code>{'{b}…{/b}'}</code>, <code>{'{i}…{/i}'}</code>, <code>{'{u}…{/u}'}</code>: select text and use the toolbar. <code>{'{icon …}'}</code> and <code>{'{hide}'}</code> style the whole component.</p>
									</details>
								</div>
								{/if}
								{#if sel.rules?.length}
									<div class="bg-warning/15 rounded-box flex flex-col gap-2 p-2.5 text-xs font-normal">
										This component still has {sel.rules.length} rule{sel.rules.length === 1 ? '' : 's'} from the old rules list. They work, but you can't edit them.
										<button class="btn btn-xs btn-warning" onclick={convertRules}>Turn them into a template</button>
									</div>
								{/if}
								{#if entity && typeof entity.state === 'number'}
									<details class="text-xs font-medium opacity-80">
										<summary class="cursor-pointer">Number format</summary>
										<div class="mt-2 flex flex-col gap-2">
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
									</details>
								{/if}
							{/if}
							{#if !written}
								<label class="flex flex-col gap-1 text-xs font-medium opacity-80">Title (optional, shown with the control)
									<input class="input input-sm w-full" value={sel.label ?? ''} placeholder="None" maxlength="40" oninput={(e) => setLabel(e.currentTarget.value)} />
								</label>
							{/if}
							<button class="btn btn-sm btn-error btn-outline mt-auto" onclick={remove}><Icon name="close" class="size-4" />Remove</button>
						{:else}
							<p class="text-sm opacity-60">Tap a component on the card to change what it shows and how. Drag it to move it, drag its edges to resize it. The + beside the card makes the card bigger. Arrow keys nudge it, Delete removes it.</p>
						{/if}
					</section>
				</aside>
		</div>
	</div>
{/if}
