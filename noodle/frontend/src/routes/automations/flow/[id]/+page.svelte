<script lang="ts">
	import '@xyflow/svelte/dist/style.css';
	import { Background, Controls, MiniMap, SvelteFlow, type Edge, type Node } from '@xyflow/svelte';
	import { untrack, type Snippet } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import Icon from '#lib/Icon.svelte';
	import { ago, api, iconFor } from '#lib/api.ts';
	import { live } from '#lib/live.svelte.ts';
	import { accepts, activeOutputs, CATALOG, defaultChanges, outputs, pressOptions, inputs, CATEGORY_NAME, CATEGORY_STYLE, DEFS, isNumeric, NODE_ICON } from '#lib/flow/catalog.ts';
	import { pluginNodes } from '#lib/flow/nodes.svelte.ts';
	import FlowNode from '#lib/flow/FlowNode.svelte';
	import WireEdge from '#lib/flow/WireEdge.svelte';
	import NodeInspector from '#lib/flow/NodeInspector.svelte';
	import { pick as picking } from '#lib/flow/pick.svelte.ts';
	import { activity, applyActivity, resetActivity } from '#lib/flow/activity.svelte.ts';

	type Flow = { id: string; name: string; enabled: boolean; last_run: number | null; last_error: string | null;
		graph: { nodes: Node[]; edges: Edge[] } };
	type LogLine = { time: number; message: string };

	// Nodes that integrations add join the catalog once they are loaded.
	const nodeTypes = $derived.by(() => {
		void pluginNodes.version;
		return Object.fromEntries(CATALOG.map((d) => [d.type, FlowNode]));
	});
	const catalog = $derived.by(() => {
		void pluginNodes.version;
		return CATALOG.filter((d) => d.available !== false);
	});
	const edgeTypes = { wire: WireEdge };

	let flow = $state<Flow | null>(null);
	let name = $state('');
	let nodes = $state.raw<Node[]>([]);
	let edges = $state.raw<Edge[]>([]);
	let selectedId = $state<string | null>(null);

	// Resting the pointer on a wire for half a second "focuses" it: the others fade, so it is easy to follow. Sweeping
	// over several wires does nothing, because each new wire restarts the wait.
	const FOCUS_AFTER_MS = 500;
	let focusedEdge = $state<string | null>(null);
	let focusTimer: ReturnType<typeof setTimeout> | undefined;
	function wireEnter(id: string) {
		clearTimeout(focusTimer);
		focusTimer = setTimeout(() => (focusedEdge = id), FOCUS_AFTER_MS);
	}
	function wireLeave() {
		clearTimeout(focusTimer);
		focusedEdge = null;
	}
	let saved = $state('');
	let error = $state('');
	let logs = $state<LogLine[]>([]);
	let showLog = $state(false);

	// Every wire has its own colour. A wire glows when its output is true right now (motion, too cold, between these
	// times...), flows brightly just after a message went along, and is dashed while a timer is counting down.
	const byId = $derived(Object.fromEntries(nodes.map((n) => [n.id, n])));
	function edgeClass(e: Edge, i: number) {
		const wire = `wire-${i % 8}${e.id === focusedEdge ? ' focused' : ''}`; // each wire its own colour
		if (activity.passed.includes(e.id)) return `${wire} fired`;
		if (e.source in activity.waiting) return `${wire} waiting`;
		const n = byId[e.source];
		return n && activeOutputs(n.type ?? '', n.id, n.data, live.devices).includes(e.sourceHandle ?? 'out') ? `${wire} active` : wire;
	}
	$effect(() => {
		if (edges.some((e, i) => (e.class ?? '') !== edgeClass(e, i))) edges = edges.map((e, i) => ({ ...e, class: edgeClass(e, i) }));
	});

	// Remember pan and zoom per flow, so the canvas opens where it was left.
	const viewKey = `flow-view:${page.params.id}`;
	const savedView = (() => {
		try {
			return JSON.parse(localStorage.getItem(viewKey) ?? 'null') as { x: number; y: number; zoom: number } | null;
		} catch {
			return null;
		}
	})();
	let viewport = $state(savedView ?? { x: 0, y: 0, zoom: 1 });
	let canvas = $state<HTMLDivElement>();
	const rememberView = (_: unknown, v: { x: number; y: number; zoom: number }) => {
		try {
			localStorage.setItem(viewKey, JSON.stringify(v));
		} catch {
			/* storage unavailable */
		}
	};

	const graph = () => ({
		nodes: nodes.map((n) => ({ id: n.id, type: n.type, position: n.position, data: n.data })),
		edges: edges.map((e) => ({ id: e.id, source: e.source, sourceHandle: e.sourceHandle ?? 'out', target: e.target, ...(e.targetHandle ? { targetHandle: e.targetHandle } : {}) }))
	});
	/** What counts as a change: the name, nodes (with where they are), and connections. */
	const fingerprint = () => {
		const g = graph();
		return JSON.stringify([name, g.nodes.map((n) => ({ ...n, position: { x: Math.round(n.position.x), y: Math.round(n.position.y) } })), g.edges]);
	};
	const dirty = $derived(flow !== null && fingerprint() !== saved);
	const selected = $derived(nodes.find((n) => n.id === selectedId) ?? null);


	async function load() {
		await pluginNodes.ensure();
		flow = await api<Flow>(`/flows/${page.params.id}`);
		if (!live.flows) api<typeof live.flows>('/flows').then((f) => (live.flows ??= f)).catch(() => {});
		name = flow.name;
		nodes = flow.graph.nodes ?? [];
		edges = (flow.graph.edges ?? []).map((e) => ({ ...e, type: 'wire', id: e.id ?? `${e.source}-${e.sourceHandle}-${e.target}` }));
		saved = fingerprint();
	}

	async function save() {
		error = '';
		try {
			flow = await api<Flow>(`/flows/${page.params.id}`, { method: 'PUT', body: { name, graph: graph() } });
			saved = fingerprint();
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}

	async function setEnabled(enabled: boolean) {
		if (dirty) await save();
		flow = await api<Flow>(`/flows/${page.params.id}`, { method: 'PUT', body: { enabled } });
	}

	async function remove() {
		if (!confirm(`Delete flow "${name}"?`)) return;
		await api(`/flows/${page.params.id}`, { method: 'DELETE' });
		goto('/automations');
	}

	type Pick = { device_id: string; key: string };
	type Payload = { type: string; pick?: Pick };

	const snap = (v: number) => Math.round(v / 20) * 20;

	function build(type: string, pick?: Pick, at?: { x: number; y: number }) {
		const id = `n${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`;
		const data: Record<string, any> = { ...DEFS[type].defaults };
		if (pick) {
			const dev = live.devices[pick.device_id];
			data.device_id = pick.device_id;
			data.key = pick.key;
			if (type === 'trigger.state') {
				data.outputs = defaultChanges(dev);
				delete data.key;
			}
			if (type === 'trigger.event') {
				data.outputs = pressOptions(dev).slice(0, 1).map((o) => o.id);
				delete data.key;
			}
			if (type === 'cond.state' && isNumeric(dev?.entities.find((e) => e.key === pick.key))) data.op = 'gt';
		}
		// Dropped on the canvas: where it was dropped. Added with +: to the right of that node (below the steps that already
		// follow the same output). Otherwise: under everything else. From there it can be dragged anywhere.
		const from = picking.from;
		const heightOf = (n: Node) => n.measured?.height ?? 160;
		let position = at ? { x: snap(at.x), y: snap(at.y) } : {
			x: nodes.length ? Math.min(...nodes.map((n) => n.position.x)) : 0,
			y: nodes.length ? snap(Math.max(...nodes.map((n) => n.position.y + heightOf(n))) + 40) : 0
		};
		const edge: Edge[] = [];
		if (from) {
			const source = nodes.find((n) => n.id === from.id);
			const siblings = edges.filter((e) => e.source === from.id && e.sourceHandle === from.handle).map((e) => byId[e.target]).filter(Boolean);
			position = {
				x: snap((source?.position.x ?? 0) + 380),
				y: siblings.length ? snap(Math.max(...siblings.map((n) => n.position.y + heightOf(n))) + 40) : snap(source?.position.y ?? 0)
			};
			const target = inputs(type, data)[0]?.id;
			edge.push({ id: `${from.id}-${from.handle}-${id}${target ? '-' + target : ''}`, type: 'wire', source: from.id, sourceHandle: from.handle, target: id, ...(target ? { targetHandle: target } : {}) });
		}
		nodes = [...nodes.map((n) => ({ ...n, selected: false })), { id, type, position, data, selected: true }];
		edges = [...edges, ...edge];
		selectedId = id;
		addOpen = false;
		picking.from = null;
	}

	const add = (type: string, pick?: Pick) => build(type, pick);

	// --- side panels: the palette (left) and the properties (right) can be dragged wider; widths are remembered.
	// Node types that need a device expand into a list of devices to drag out.
	const storedWidth = (key: string, fallback: number) => {
		try {
			return Number(localStorage.getItem(key)) || fallback;
		} catch {
			return fallback;
		}
	};
	let paletteWidth = $state(storedWidth('flow-palette-width', 288));
	let panelWidth = $state(storedWidth('flow-panel-width', 288));

	/** Drag a separator; `side` says which panel it resizes (the right one grows when dragged to the left). */
	function resize(e: PointerEvent, side: 'palette' | 'panel') {
		e.preventDefault();
		const startX = e.clientX, startWidth = side === 'palette' ? paletteWidth : panelWidth;
		const move = (ev: PointerEvent) => {
			const delta = side === 'palette' ? ev.clientX - startX : startX - ev.clientX;
			const width = Math.min(640, Math.max(220, startWidth + delta));
			if (side === 'palette') paletteWidth = width;
			else panelWidth = width;
		};
		const up = () => {
			window.removeEventListener('pointermove', move);
			window.removeEventListener('pointerup', up);
			try {
				localStorage.setItem(`flow-${side}-width`, String(side === 'palette' ? paletteWidth : panelWidth));
			} catch {
				/* storage unavailable */
			}
		};
		window.addEventListener('pointermove', move);
		window.addEventListener('pointerup', up);
	}

	let menu = $state<HTMLDetailsElement>();
	let addOpen = $state(false); // phone: the palette is a sheet that slides up
	let open = $state<string | null>(null);
	let search = $state('');

	/** Devices a node type can use, each with the entities to pick from (one entity = no submenu). */
	function choices(type: string) {
		const q = search.trim().toLowerCase();
		return live.list
			.map((d) => ({ d, entities: d.entities.filter((e) => accepts(DEFS[type], e)) }))
			.filter(({ d, entities }) => entities.length && (d.name + ' ' + (d.area ?? '')).toLowerCase().includes(q))
			// Buttons and "Device changes" pick what to react to in their properties, so the device alone is enough.
			.map(({ d, entities }) => ({ d, entities: type === 'trigger.event' || type === 'trigger.state' ? entities.slice(0, 1) : entities }));
	}
	let openDevice = $state<string | null>(null);

	function toggleOpen(type: string) {
		open = open === type ? null : type;
		openDevice = null;
		search = '';
	}

	function dragStart(e: DragEvent, payload: Payload) {
		e.dataTransfer?.setData('application/x-noodle-node', JSON.stringify(payload));
		if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copy';
	}

	function dropOnCanvas(e: DragEvent) {
		const raw = e.dataTransfer?.getData('application/x-noodle-node');
		if (!raw) return;
		e.preventDefault();
		const { type, pick } = JSON.parse(raw) as Payload;
		const rect = canvas!.getBoundingClientRect();
		const snap = (v: number) => Math.round(v / 20) * 20;
		build(type, pick, {
			x: snap((e.clientX - rect.left - viewport.x) / viewport.zoom - 128),
			y: snap((e.clientY - rect.top - viewport.y) / viewport.zoom - 40)
		});
	}

	function updateData(data: Record<string, any>) {
		nodes = nodes.map((n) => (n.id === selectedId ? { ...n, data } : n));
		// Connections into an input that was just removed (e.g. an unticked action) go too.
		const node = nodes.find((n) => n.id === selectedId);
		const ins = node ? inputs(node.type ?? '', data).map((i) => i.id) : [];
		if (ins.length) edges = edges.filter((e) => e.target !== selectedId || ins.includes(e.targetHandle ?? ''));
		// Likewise connections out of an unticked change.
		if (node?.type === 'trigger.state' || node?.type === 'trigger.event') {
			const outs = outputs(node.type, data, live.devices).map((o) => o.id);
			edges = edges.filter((e) => e.source !== selectedId || outs.includes(e.sourceHandle ?? ''));
		}
	}

	// --- copy, paste, duplicate. The clipboard is kept in the browser, so nodes can be pasted into another flow.
	type Clip = { nodes: Node[]; edges: Edge[] };
	const CLIP_KEY = 'flow-clipboard';
	const picked = () => nodes.filter((n) => n.selected || n.id === selectedId);
	let clip = $state.raw<Clip | null>(
		(() => {
			try {
				return JSON.parse(localStorage.getItem(CLIP_KEY) ?? 'null') as Clip | null;
			} catch {
				return null;
			}
		})()
	);
	let pointer: { x: number; y: number } | null = null; // last mouse position on the canvas, in flow coordinates

	function copy() {
		const chosen = picked();
		if (!chosen.length) return;
		const ids = new Set(chosen.map((n) => n.id));
		clip = {
			nodes: chosen.map((n) => ({ id: n.id, type: n.type, position: n.position, data: $state.snapshot(n.data) })),
			// Connections between the copied nodes come along; connections to other nodes do not.
			edges: edges.filter((e) => ids.has(e.source) && ids.has(e.target)).map((e) => ({ ...e }))
		};
		try {
			localStorage.setItem(CLIP_KEY, JSON.stringify(clip));
		} catch {
			/* storage unavailable: the copy still works on this page */
		}
	}

	/** Add copies of nodes (and the connections between them). */
	function place(source: Clip, at: { x: number; y: number } | null) {
		if (!source.nodes.length) return;
		const stamp = Date.now().toString(36);
		const ids = new Map(source.nodes.map((n, i) => [n.id, `n${stamp}${i}`]));
		const minX = Math.min(...source.nodes.map((n) => n.position.x));
		const minY = Math.min(...source.nodes.map((n) => n.position.y));
		const snap = (v: number) => Math.round(v / 20) * 20;
		const maxY = Math.max(...source.nodes.map((n) => n.position.y));
		// At the mouse, or else just below the originals so they do not overlap.
		const dx = at ? snap(at.x) - minX : 0, dy = at ? snap(at.y) - minY : snap(maxY - minY + 200);
		const added = source.nodes.map((n) => ({
			id: ids.get(n.id)!, type: n.type, data: JSON.parse(JSON.stringify(n.data)), selected: true,
			position: { x: n.position.x + dx, y: n.position.y + dy }
		}));
		const links = source.edges.map((e) => {
			const s = ids.get(e.source)!, t = ids.get(e.target)!;
			return { id: `${s}-${e.sourceHandle ?? 'out'}-${t}${e.targetHandle ? '-' + e.targetHandle : ''}`, type: 'wire', source: s,
				sourceHandle: e.sourceHandle, target: t, ...(e.targetHandle ? { targetHandle: e.targetHandle } : {}) };
		});
		nodes = [...nodes.map((n) => ({ ...n, selected: false })), ...added];
		edges = [...edges, ...links];
		selectedId = added.length === 1 ? added[0].id : null;
	}

	const paste = () => clip && place(clip, pointer);
	function duplicate() {
		const before = clip;
		copy();
		if (clip) place(clip, null);
		clip = before; // duplicating leaves the clipboard as it was
	}

	function selectAll() {
		nodes = nodes.map((n) => ({ ...n, selected: true }));
		selectedId = nodes.length === 1 ? nodes[0].id : null;
	}

	function toggleLog() {
		showLog = !showLog;
		if (showLog) {
			selectedId = null;
			loadLog();
		}
	}

	let openMenu = $state<string | null>(null); // the menu bar entry that is dropped down

	function onkey(e: KeyboardEvent) {
		if (e.key === 'Escape') openMenu = null;
		const t = e.target as HTMLElement;
		if (!(e.ctrlKey || e.metaKey)) return;
		const key = e.key.toLowerCase();
		if (key === 's') {
			e.preventDefault();
			if (dirty) save();
			return;
		}
		if (t.closest('input, textarea, select, [contenteditable]')) return;
		// Only take over the shortcut when there is something to copy or paste, so copying text still works.
		if (key === 'a' && nodes.length) selectAll();
		else if (key === 'c' && picked().length) copy();
		else if (key === 'v' && clip) paste();
		else if (key === 'd' && picked().length) duplicate();
		else return;
		e.preventDefault();
	}

	function trackPointer(e: PointerEvent) {
		const rect = canvas!.getBoundingClientRect();
		pointer = { x: (e.clientX - rect.left - viewport.x) / viewport.zoom, y: (e.clientY - rect.top - viewport.y) / viewport.zoom };
	}

	/** Remove the chosen nodes (one or several) and the connections to them. */
	function deletePicked() {
		const ids = new Set(picked().map((n) => n.id));
		edges = edges.filter((e) => !ids.has(e.source) && !ids.has(e.target));
		nodes = nodes.filter((n) => !ids.has(n.id));
		selectedId = null;
	}
	const deleteSelected = deletePicked;

	async function runFrom() {
		if (dirty) await save();
		await api(`/flows/${page.params.id}/run/${selectedId}`, { body: {} });
		await loadLog();
		showLog = true;
	}

	async function loadLog() {
		logs = await api<LogLine[]>(`/flows/${page.params.id}/log`);
	}

	$effect(() => {
		load().catch((err) => (error = err.message));
		// New log lines arrive over the live WebSocket.
		const onLog = (flowId: string, line: LogLine) => {
			if (flowId === page.params.id) logs = [line, ...logs].slice(0, 200);
		};
		live.logListeners.add(onLog);
		// What is happening right now; after this, changes come in over the live WebSocket.
		resetActivity(page.params.id);
		api<{ passed: string[]; waiting: Record<string, number>; zones: Record<string, string> }>(`/flows/${page.params.id}/activity`)
			.then((a) => applyActivity(page.params.id ?? '', a.passed, a.waiting, a.zones))
			.catch(() => {});
		return () => {
			live.logListeners.delete(onLog);
			resetActivity();
		};
	});
</script>

<svelte:window onkeydown={onkey} onclick={() => (openMenu = null)} />

		{#snippet palette()}
			{#each (picking.from ? ['condition', 'action'] : ['trigger', 'condition', 'action']) as cat (cat)}
				<div class="mt-3 flex items-center gap-2 px-1 text-xs font-bold tracking-wide uppercase opacity-70">
					<span class="size-2 rounded-full {CATEGORY_STYLE[cat as 'trigger' | 'condition' | 'action']}"></span>{CATEGORY_NAME[cat as 'trigger' | 'condition' | 'action']}
				</div>
				{#each catalog.filter((d) => d.category === cat) as def (def.type)}
					{@const picker = !!def.kinds}
					<button class="btn btn-sm btn-ghost cursor-grab justify-start gap-2 px-2 font-normal"
						class:btn-active={open === def.type} draggable="true"
						ondragstart={(e) => dragStart(e, { type: def.type })}
						onclick={() => (picker ? toggleOpen(def.type) : add(def.type))}
						aria-expanded={picker ? open === def.type : undefined}>
						<Icon name={NODE_ICON[def.type] ?? 'circle'} class="size-4 opacity-70" />
						<span class="grow text-left">{def.label}</span>
						{#if picker}<Icon name={open === def.type ? 'up' : 'down'} class="size-4 opacity-60" />{/if}
					</button>
					{#if picker && open === def.type}
						{@const list = choices(def.type)}
						<div class="bg-base-200 rounded-field mb-1 flex flex-col gap-1 p-1.5">
							<p class="px-1 text-[11px] opacity-60">Drag a device onto the canvas, or tap it.</p>
							<input type="search" class="input input-xs w-full" placeholder="Search devices" bind:value={search} />
							<div class="flex max-h-64 flex-col overflow-y-auto">
								{#each list as c (c.d.id)}
									{@const single = c.entities.length === 1}
									<button class="btn btn-ghost btn-xs h-auto min-h-8 cursor-grab justify-start gap-2 py-1 text-left font-normal"
										draggable={single}
										ondragstart={(e) => single && dragStart(e, { type: def.type, pick: { device_id: c.d.id, key: c.entities[0].key } })}
										onclick={() => (single ? add(def.type, { device_id: c.d.id, key: c.entities[0].key }) : (openDevice = openDevice === c.d.id ? null : c.d.id))}
										aria-expanded={single ? undefined : openDevice === c.d.id}>
										<Icon name={iconFor(c.d)} class="size-4 shrink-0 opacity-70" />
										<span class="min-w-0 grow"><span class="block truncate">{c.d.name}</span>
											{#if c.d.area}<span class="block truncate text-[10px] opacity-50">{c.d.area}</span>{/if}</span>
										{#if !single}<Icon name={openDevice === c.d.id ? 'up' : 'down'} class="size-4 shrink-0 opacity-60" />{/if}
									</button>
									{#if !single && openDevice === c.d.id}
										<div class="border-base-content/15 mb-1 ml-4 flex flex-col border-l pl-1">
											{#each c.entities as e (e.key)}
												<button class="btn btn-ghost btn-xs cursor-grab justify-start font-normal" draggable="true"
													ondragstart={(ev) => dragStart(ev, { type: def.type, pick: { device_id: c.d.id, key: e.key } })}
													onclick={() => add(def.type, { device_id: c.d.id, key: e.key })}>{e.name}</button>
											{/each}
										</div>
									{/if}
								{:else}
									<p class="p-2 text-xs opacity-60">No matching devices.</p>
								{/each}
							</div>
						</div>
					{/if}
				{/each}
			{/each}
		{/snippet}

{#if flow}
	<!-- The editor takes the whole screen (next to the side menu on a desktop), covering the app header and tab bar. -->
	<div class="bg-base-200 fixed inset-0 z-40 flex flex-col gap-2 p-2 lg:left-60">
	<!-- Phone: one slim bar; everything secondary lives in the ⋯ menu. -->
	<div class="relative z-30 flex items-center gap-2 md:hidden">
		<a href="/automations" class="btn btn-ghost btn-square" aria-label="Back to automations"><Icon name="left" class="size-5" /></a>
		<input class="input min-w-0 grow font-bold" bind:value={name} aria-label="Flow name" />
		<button class="btn btn-primary" disabled={!dirty} onclick={save}>{dirty ? 'Save' : 'Saved'}</button>
		<details class="dropdown dropdown-end" bind:this={menu}>
			<summary class="btn btn-ghost btn-square list-none" aria-label="More"><Icon name="dots" class="size-7" /></summary>
			<ul class="menu dropdown-content bg-base-100 rounded-box border-base-content/10 z-50 mt-2 w-64 gap-1 border p-2 shadow-xl" onclick={() => menu && (menu.open = false)} role="presentation">
				<li><label class="flex justify-between"><span>{flow.enabled ? 'Flow is on' : 'Flow is off'}</span>
					<input type="checkbox" class="toggle toggle-primary" checked={flow.enabled} onchange={(e) => setEnabled(e.currentTarget.checked)} /></label></li>
				<li class="menu-title">Nodes</li>
				<li class:menu-disabled={!picked().length}><button disabled={!picked().length} onclick={copy}>Copy selected</button></li>
				<li class:menu-disabled={!clip}><button disabled={!clip} onclick={() => clip && place(clip, null)}>Paste</button></li>
				<li class:menu-disabled={!picked().length}><button disabled={!picked().length} onclick={duplicate}>Duplicate selected</button></li>
				<li class="menu-title">Flow</li>
				<li><button onclick={() => { showLog = !showLog; selectedId = null; if (showLog) loadLog(); }}>Log</button></li>
				<li><button class="text-error" onclick={remove}>Delete flow</button></li>
				<li class="px-3 pt-1 text-xs opacity-60">Last run: {ago(flow.last_run)}</li>
			</ul>
		</details>
	</div>

	<!-- Desktop: an application-style menu bar. -->
	{#snippet entry(label: string, keys: string, action: () => void, disabled = false, danger = false)}
		<li class:menu-disabled={disabled}>
			<button class="flex justify-between gap-8 {danger ? 'text-error' : ''}" {disabled} onclick={() => { openMenu = null; action(); }}>
				<span>{label}</span>{#if keys}<kbd class="kbd kbd-sm">{keys}</kbd>{/if}
			</button>
		</li>
	{/snippet}
	{#snippet bar(id: string, title: string, items: Snippet)}
		<div class="relative">
			<button class="btn btn-ghost btn-sm font-normal" class:btn-active={openMenu === id}
				onclick={() => (openMenu = openMenu === id ? null : id)} onpointerenter={() => openMenu && (openMenu = id)}>{title}</button>
			{#if openMenu === id}
				<ul class="menu bg-base-100 rounded-box border-base-content/10 absolute top-full left-0 z-50 mt-1 w-64 gap-0.5 border p-2 shadow-xl">{@render items()}</ul>
			{/if}
		</div>
	{/snippet}
	{#snippet fileMenu()}
		{@render entry('Save', 'Ctrl S', save, !dirty)}
		<li><label class="flex justify-between"><span>{flow?.enabled ? 'Flow is on' : 'Flow is off'}</span>
			<input type="checkbox" class="toggle toggle-primary toggle-sm" checked={flow?.enabled} onchange={(e) => setEnabled(e.currentTarget.checked)} /></label></li>
		{@render entry('Delete flow…', '', remove, false, true)}
	{/snippet}
	{#snippet editMenu()}
		{@render entry('Copy', 'Ctrl C', copy, !picked().length)}
		{@render entry('Paste', 'Ctrl V', paste, !clip)}
		{@render entry('Duplicate', 'Ctrl D', duplicate, !picked().length)}
		{@render entry('Select all', 'Ctrl A', selectAll, !nodes.length)}
		{@render entry('Delete', 'Del', deletePicked, !picked().length, true)}
	{/snippet}
	{#snippet viewMenu()}
		{@render entry(showLog ? 'Hide log' : 'Show log', '', toggleLog)}
	{/snippet}

	<!-- svelte-ignore a11y_no_static_element_interactions, a11y_click_events_have_key_events -->
	<div class="bg-base-100 border-base-content/10 rounded-box relative z-30 flex items-center gap-1 border px-2 py-1 max-md:hidden" onclick={(e) => e.stopPropagation()}>
		<a href="/automations" class="btn btn-ghost btn-sm btn-square" aria-label="Back to automations" title="Back to automations"><Icon name="left" class="size-4" /></a>
		<input class="input input-sm w-56 font-bold" bind:value={name} aria-label="Flow name" />
		<div class="ml-1 flex items-center">
			{@render bar('file', 'File', fileMenu)}
			{@render bar('edit', 'Edit', editMenu)}
			{@render bar('view', 'View', viewMenu)}
		</div>
		<span class="ml-auto text-xs opacity-60 max-lg:hidden">Last run: {ago(flow.last_run)}</span>
		<label class="label mx-2 gap-2 text-sm">
			<input type="checkbox" class="toggle toggle-primary toggle-sm" checked={flow.enabled} onchange={(e) => setEnabled(e.currentTarget.checked)} />
			{flow.enabled ? 'On' : 'Off'}
		</label>
		<button class="btn btn-sm btn-primary" disabled={!dirty} onclick={save} title="Save (Ctrl+S)">{dirty ? 'Save' : 'Saved'}</button>
	</div>
	{#if error || flow.last_error}<div role="alert" class="alert alert-error alert-soft mb-3 text-sm">{error || flow.last_error}</div>{/if}

	<div class="flex min-h-0 grow gap-3">
		<aside class="bg-base-100 border-base-content/10 rounded-box hidden shrink-0 flex-col gap-1 overflow-y-auto border p-2 md:flex" style="width: {paletteWidth}px">
			{@render palette()}
		</aside>

		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="-mx-1.5 hidden w-3 shrink-0 cursor-col-resize items-center justify-center md:flex" onpointerdown={(e) => resize(e, 'palette')}
			title="Drag to resize" role="separator" aria-orientation="vertical">
			<span class="bg-base-content/20 hover:bg-primary h-10 w-1 rounded-full"></span>
		</div>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="bg-base-100 border-base-content/10 rounded-box min-w-0 grow overflow-hidden border" class:wire-focus={focusedEdge !== null} bind:this={canvas}
			onpointermove={trackPointer} onpointerleave={() => (pointer = null)}
			ondragover={(e) => { if (e.dataTransfer?.types.includes('application/x-noodle-node')) e.preventDefault(); }}
			ondrop={dropOnCanvas}>
			<SvelteFlow bind:nodes bind:edges {nodeTypes} {edgeTypes} fitView={!savedView} bind:viewport
				snapGrid={[20, 20]} onmoveend={rememberView} connectionRadius={40}
					defaultEdgeOptions={{ type: 'wire' }} colorMode="system" deleteKey={['Delete', 'Backspace']}
				onnodeclick={({ node }) => (selectedId = node.id)} onpaneclick={() => (selectedId = null)}
				onedgepointerenter={({ edge }) => wireEnter(edge.id)} onedgepointerleave={wireLeave}>
				<Background />
				<Controls class="max-md:hidden!" />
				<MiniMap class="max-md:hidden!" />
			</SvelteFlow>
		</div>

		{#if selected || showLog}
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div class="-mx-1.5 hidden w-3 shrink-0 cursor-col-resize items-center justify-center md:flex" onpointerdown={(e) => resize(e, 'panel')}
				title="Drag to resize" role="separator" aria-orientation="vertical">
				<span class="bg-base-content/20 hover:bg-primary h-10 w-1 rounded-full"></span>
			</div>
			<aside class="bg-base-100 border-base-content/10 rounded-box overflow-x-hidden overflow-y-auto border p-3 shadow-2xl max-md:fixed max-md:inset-x-2 max-md:bottom-2 max-md:z-50 max-md:max-h-[50dvh] md:w-[var(--w)] md:shrink-0 md:shadow-none" style="--w: {panelWidth}px">
				<button class="btn btn-ghost btn-sm btn-circle absolute top-1 right-1 md:hidden" aria-label="Close"
					onclick={() => { selectedId = null; showLog = false; }}><Icon name="close" class="size-5" /></button>
				{#if selected}
					<NodeInspector type={selected.type ?? ''} data={selected.data} onchange={updateData} ondelete={deleteSelected} onduplicate={duplicate}
						onrun={DEFS[selected.type ?? '']?.category === 'trigger' ? runFrom : undefined} />
				{/if}
				{#if showLog}
					<h3 class="mt-4 mb-1 font-bold">Log</h3>
					<div class="flex flex-col gap-1 text-xs">
						{#each logs as l (l.time + l.message)}
							<div><span class="opacity-60">{new Date(l.time * 1000).toLocaleTimeString()}</span> {l.message}</div>
						{:else}<div class="opacity-60">Nothing yet.</div>{/each}
					</div>
				{/if}
			</aside>
		{/if}
	</div>
	{#if !selected && !showLog && !addOpen}
		<div class="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center md:hidden">
			<button class="btn btn-primary btn-lg pointer-events-auto rounded-full px-8 shadow-xl" onclick={() => (addOpen = true)}>
				<Icon name="plus" class="size-6" />Add node
			</button>
		</div>
	{/if}
	{#if picking.from}
		<!-- "+" next to an output: choose what comes next; it is created and connected for you. -->
		<div class="fixed inset-0 z-[60] flex items-end justify-center md:items-center">
			<button class="absolute inset-0 bg-black/30" aria-label="Close" onclick={() => (picking.from = null)}></button>
			<aside class="bg-base-100 border-base-content/10 rounded-box relative flex max-h-[75dvh] w-full max-w-md flex-col gap-1 overflow-y-auto border p-3 shadow-2xl max-md:mx-2 max-md:mb-2">
				<div class="flex items-center justify-between px-1">
					<h3 class="font-bold">What happens next?</h3>
					<button class="btn btn-ghost btn-sm btn-circle" aria-label="Close" onclick={() => (picking.from = null)}><Icon name="close" class="size-5" /></button>
				</div>
				{@render palette()}
			</aside>
		</div>
	{/if}
	{#if addOpen}
		<div class="fixed inset-0 z-[60] md:hidden">
			<button class="absolute inset-0 bg-black/20" aria-label="Close" onclick={() => (addOpen = false)}></button>
			<aside class="bg-base-100 border-base-content/10 rounded-box absolute inset-x-2 bottom-2 flex max-h-[65dvh] flex-col gap-1 overflow-y-auto border p-3 shadow-2xl">
				<div class="flex items-center justify-between px-1">
					<h3 class="font-bold">Nodes</h3>
					<button class="btn btn-ghost btn-sm btn-circle" aria-label="Close" onclick={() => (addOpen = false)}><Icon name="close" class="size-5" /></button>
				</div>
				{@render palette()}
			</aside>
		</div>
	{/if}
	</div>
{:else if error}
	<div role="alert" class="alert alert-error alert-soft">{error}</div>
{:else}
	<div class="flex justify-center py-20"><span class="loading loading-dots loading-lg text-primary"></span></div>
{/if}
