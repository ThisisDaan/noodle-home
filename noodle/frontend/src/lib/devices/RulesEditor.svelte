<script lang="ts">
	import Icon from '../Icon.svelte';
	import type { Device, Entity } from '../api.ts';
	import { COLORS, ICONS, type CardColor } from './cardDesign.ts';
	import FieldPicker from './FieldPicker.svelte';
	import { TOKENS, fieldName, fieldsOf, locate } from './cardText.ts';
	import { parseRules, serializeRules, type Branch, type Clause, type Op, type RuleSet } from './rules.ts';

	/** The rules view of a component's text: "when … then …" cards you can reorder, and an "otherwise". It reads and
	 * writes the same template text as the code box. */
	let { template, device, devices, entity, hasFill, onchange }: {
		template: string;
		device: Device;
		/** every device, for picking a value of another one */
		devices: Device[];
		/** the field the component shows (what "This value" means) */
		entity?: Entity;
		/** whether the component has something to fill (a slider, bar, gauge, power button) */
		hasFill: boolean;
		onchange: (text: string) => void;
	} = $props();

	const set = $derived(parseRules(template));
	const fields = $derived(fieldsOf(device));
	const kindOf = (ref: string): 'bool' | 'number' | 'text' => {
		const f = ref === 'value' ? entity : locate(device, ref)?.entity;
		return typeof f?.state === 'boolean' ? 'bool' : typeof f?.state === 'number' ? 'number' : 'text';
	};
	const valueSpecials = $derived([{ ref: 'value', label: entity?.name ?? 'This value' }]);
	const textSpecials = TOKENS.map((t) => ({ ref: t.token.slice(1, -1), label: t.label }));

	// The text to show is a row of words and values: words are typed, a value is picked (device, then field).
	// texts[i] sits before tags[i]; there is always one more text than tags.
	const split = (src: string) => {
		const tags = [...src.matchAll(/\{[^{}]*\}/g)].map((m) => m[0].slice(1, -1));
		return { texts: src.split(/\{[^{}]*\}/), tags };
	};
	const join = (texts: string[], tags: string[]) => texts.map((t, i) => t + (i < tags.length ? `{${tags[i]}}` : '')).join('');
	/** a tag that is a value (one that picks a field), as opposed to a style like {b} or {color x} */
	const isValue = (tag: string) => textSpecials.some((s) => s.ref === tag) || !!locate(device, tag.replace(/\.history.*$/, '')) && !/\.history/.test(tag);
	const OPS: { op: Op; label: string }[] = [
		{ op: '==', label: 'is' }, { op: '!=', label: 'is not' }, { op: '>', label: 'is above' },
		{ op: '<', label: 'is below' }, { op: '>=', label: 'is at least' }, { op: '<=', label: 'is at most' }
	];
	const TEXT_OPS = OPS.filter((o) => o.op === '==' || o.op === '!=');
	const NUMBER_OPS = OPS;

	function commit(next: RuleSet) {
		onchange(serializeRules(next));
	}
	/** change a copy of the rules and write them out */
	function edit(fn: (s: RuleSet) => void) {
		if (!set) return;
		const next = structuredClone($state.snapshot(set)) as RuleSet;
		fn(next);
		commit(next);
	}
	const firstClause = (): Clause => {
		const ref = entity ? 'value' : fields[0] ? fieldName(device, fields[0]) : 'value';
		const k = kindOf(ref);
		return { field: ref, op: k === 'number' ? '>' : '==', value: k === 'bool' ? 'true' : k === 'number' ? '0' : '' };
	};
	const addRule = () => edit((s) => s.rules.push({ join: 'and', clauses: [firstClause()], then: { text: entity ? '{value}' : '' } }));
	function setField(c: Clause, ref: string) {
		const k = kindOf(ref);
		c.field = ref;
		c.op = k === 'number' ? '>' : '==';
		c.value = k === 'bool' ? 'true' : k === 'number' ? '0' : '';
	}
	function move(i: number, to: number) {
		if (to < 0 || to >= (set?.rules.length ?? 0) || to === i) return;
		edit((s) => { const [r] = s.rules.splice(i, 1); s.rules.splice(to, 0, r); });
	}

	let dragging = $state<number | null>(null);
	let over = $state<number | null>(null);

	/** what a new "A value" shows first: this component's own field, else the device's first */
	const defaultRef = $derived(entity ? 'value' : fields[0] ? fieldName(device, fields[0]) : 'value');
	const editText = (b: Branch, fn: (texts: string[], tags: string[]) => void) => {
		const { texts, tags } = split(b.text);
		fn(texts, tags);
		b.text = join(texts, tags);
	};
	const label = (c?: string) => c ?? 'none';
</script>

{#snippet swatch(title: string, current: string | undefined, pick: (c?: string) => void)}
	<details class="dropdown">
		<summary class="btn btn-sm gap-1.5 px-2 font-normal" aria-label="{title}: {label(current)}">
			<span class="size-4 rounded-full border border-base-content/30 {current && current in COLORS ? COLORS[current as CardColor].dot : ''}" style={current && !(current in COLORS) ? `background:${current}` : ''}></span>
			<span class="text-xs">{title}</span>
		</summary>
		<div class="dropdown-content bg-base-100 rounded-box z-10 mt-1 flex w-48 flex-wrap gap-1.5 p-2 shadow-lg" role="group" aria-label={title}>
			<button class="btn btn-xs btn-circle btn-outline" aria-label="No {title.toLowerCase()}" title="None" onclick={(e) => { pick(); e.currentTarget.closest('details')?.removeAttribute('open'); }}><Icon name="close" class="size-3" /></button>
			{#each Object.keys(COLORS) as c (c)}
				<button class="size-6 rounded-full border-2 {COLORS[c as CardColor].dot} {current === c ? 'border-base-content' : 'border-transparent'}" aria-label={c} title={c} onclick={(e) => { pick(c); e.currentTarget.closest('details')?.removeAttribute('open'); }}></button>
			{/each}
			<label class="flex items-center gap-1 text-xs font-normal" title="Any colour"><input type="color" class="h-6 w-8 cursor-pointer rounded" value={current && !(current in COLORS) && /^#[0-9a-f]{6}$/i.test(current) ? current : '#3b82f6'} aria-label="Pick any colour" onchange={(e) => { pick(e.currentTarget.value); e.currentTarget.closest('details')?.removeAttribute('open'); }} />Any colour</label>
		</div>
	</details>
{/snippet}

{#snippet effects(b: Branch, patch: (fn: (b: Branch) => void) => void)}
	{@const parts = split(b.text)}
	{@const how = parts.tags.length === 0 ? 'text' : parts.tags.length === 1 && !parts.texts[0] && !parts.texts[1] && isValue(parts.tags[0]) ? 'value' : 'mixed'}
	<div class="flex flex-col gap-2">
		<span class="text-[11px] font-semibold tracking-wide uppercase opacity-60">Then</span>
		<div class="flex flex-wrap items-center gap-1.5">
			{@render swatch('Background', b.bg, (c) => patch((x) => (x.bg = c)))}
			{#if hasFill}{@render swatch('Fill', b.fill, (c) => patch((x) => (x.fill = c)))}{/if}
			{@render swatch('Text colour', b.color, (c) => patch((x) => (x.color = c)))}
			<select class="select select-sm w-28" aria-label="Icon" value={b.icon ?? ''} onchange={(e) => patch((x) => (x.icon = e.currentTarget.value || undefined))}>
				<option value="">No icon</option>
				{#each ICONS as i (i)}<option value={i}>{i}</option>{/each}
			</select>
			<label class="flex items-center gap-1.5 text-xs font-normal"><input type="checkbox" class="checkbox checkbox-xs" checked={!!b.hide} onchange={(e) => patch((x) => (x.hide = e.currentTarget.checked || undefined))} />Hide</label>
		</div>
		<div class="flex flex-col gap-1.5">
			<span class="text-xs opacity-70">Display</span>
			<div class="join self-start" role="group" aria-label="What to display">
				<button class="btn btn-sm join-item" class:btn-primary={how === 'value'} onclick={() => patch((x) => (x.text = `{${defaultRef}}`))}>A value</button>
				<button class="btn btn-sm join-item" class:btn-primary={how === 'text'} onclick={() => patch((x) => { if (how !== 'text') x.text = ''; })}>Text</button>
				{#if how === 'mixed'}<button class="btn btn-sm join-item btn-primary">Words and values</button>{/if}
			</div>
			{#if how === 'value'}
				<FieldPicker ref={parts.tags[0]} {device} {devices} specials={textSpecials} onpick={(r) => patch((x) => (x.text = `{${r}}`))} />
			{:else if how === 'text'}
				<input class="input input-sm w-full" value={b.text} placeholder="Type the text to show" aria-label="Text to show" oninput={(e) => patch((x) => (x.text = e.currentTarget.value))} />
			{:else}
				<div class="flex flex-wrap items-center gap-1.5">
					{#each parts.texts as t, i (i)}
						<input class="input input-sm min-w-10 max-w-full" style="field-sizing: content;" value={t} aria-label="Words"
							oninput={(e) => patch((x) => editText(x, (texts) => (texts[i] = e.currentTarget.value)))} />
						{#if i < parts.tags.length}
							<span class="bg-base-100 border-base-content/15 rounded-field flex items-center gap-1 border p-1">
								{#if isValue(parts.tags[i])}
									<FieldPicker ref={parts.tags[i]} {device} {devices} specials={textSpecials} onpick={(r) => patch((x) => editText(x, (_t, tags) => (tags[i] = r)))} />
								{:else}
									<code class="px-1.5 text-xs" title="A style or an advanced value. Change it in the text view.">{`{${parts.tags[i]}}`}</code>
								{/if}
								<button class="btn btn-ghost btn-xs btn-square" aria-label="Remove this value" onclick={() => patch((x) => editText(x, (texts, tags) => { texts.splice(i, 2, texts[i] + texts[i + 1]); tags.splice(i, 1); }))}><Icon name="close" class="size-3" /></button>
							</span>
						{/if}
					{/each}
				</div>
			{/if}
		</div>
	</div>
{/snippet}

{#if !set}
	<p class="bg-base-200 rounded-box p-2 text-xs font-normal opacity-80">This text has more in it than the rules view can show (rules inside rules, brackets or “not”). Edit it in the text view.</p>
{:else}
	<div class="flex flex-col gap-2 font-normal">
		{#each set.rules as r, i (i)}
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div class="bg-base-200/70 rounded-box border-2 p-2.5 transition-colors {over === i && dragging !== null && dragging !== i ? 'border-primary' : 'border-transparent'}" class:opacity-50={dragging === i}
				ondragover={(e) => { if (dragging !== null) { e.preventDefault(); over = i; } }}
				ondrop={(e) => { e.preventDefault(); if (dragging !== null) move(dragging, i); dragging = over = null; }}>
				<div class="mb-2 flex items-center gap-1.5">
					<span class="cursor-grab touch-none px-1 opacity-60" title="Drag to change the order" aria-hidden="true" draggable="true"
						ondragstart={(e) => { dragging = i; e.dataTransfer?.setData('text/plain', String(i)); }} ondragend={() => (dragging = over = null)}><Icon name="grip" class="size-4" /></span>
					<span class="grow text-[11px] font-semibold tracking-wide uppercase opacity-60">{i === 0 ? 'When' : 'Otherwise, when'}</span>
					<button class="btn btn-ghost btn-xs btn-square" aria-label="Move up" disabled={i === 0} onclick={() => move(i, i - 1)}>▲</button>
					<button class="btn btn-ghost btn-xs btn-square" aria-label="Move down" disabled={i === set.rules.length - 1} onclick={() => move(i, i + 1)}>▼</button>
					<button class="btn btn-ghost btn-xs btn-square" aria-label="Remove this rule" onclick={() => edit((s) => s.rules.splice(i, 1))}><Icon name="close" class="size-3.5" /></button>
				</div>
				<div class="mb-3 flex flex-col gap-1.5">
					{#each r.clauses as c, ci (ci)}
						{@const k = kindOf(c.field)}
						{#if ci > 0}
							<select class="select select-xs w-20" aria-label="And or or" value={r.join} onchange={(e) => edit((s) => (s.rules[i].join = e.currentTarget.value as 'and' | 'or'))}>
								<option value="and">and</option><option value="or">or</option>
							</select>
						{/if}
						<div class="flex flex-wrap items-center gap-1.5">
							<FieldPicker ref={c.field} {device} {devices} specials={valueSpecials} onpick={(r) => edit((s) => setField(s.rules[i].clauses[ci], r))} />
							{#if k === 'bool'}
								<select class="select select-sm w-24" aria-label="State" value={c.value === 'true' && c.op === '==' || c.value === 'false' && c.op === '!=' ? 'on' : 'off'}
									onchange={(e) => edit((s) => { const x = s.rules[i].clauses[ci]; x.op = '=='; x.value = e.currentTarget.value === 'on' ? 'true' : 'false'; })}>
									<option value="on">is on</option><option value="off">is off</option>
								</select>
							{:else}
								<select class="select select-sm w-28" aria-label="Comparison" value={c.op} onchange={(e) => edit((s) => (s.rules[i].clauses[ci].op = e.currentTarget.value as Op))}>
									{#each k === 'number' ? NUMBER_OPS : TEXT_OPS as o (o.op)}<option value={o.op}>{o.label}</option>{/each}
								</select>
								<input class="input input-sm w-24" type={k === 'number' ? 'number' : 'text'} step="any" aria-label="Value" value={c.value} placeholder="value"
									oninput={(e) => edit((s) => (s.rules[i].clauses[ci].value = e.currentTarget.value))} />
							{/if}
							{#if r.clauses.length > 1}
								<button class="btn btn-ghost btn-xs btn-square" aria-label="Remove this condition" onclick={() => edit((s) => s.rules[i].clauses.splice(ci, 1))}><Icon name="close" class="size-3.5" /></button>
							{/if}
						</div>
					{/each}
					{#if r.clauses.length < 4}
						<button class="btn btn-ghost btn-xs self-start" onclick={() => edit((s) => s.rules[i].clauses.push(firstClause()))}>+ another condition</button>
					{/if}
				</div>
				{@render effects(r.then, (fn) => edit((s) => fn(s.rules[i].then)))}
			</div>
		{/each}

		<button class="btn btn-sm btn-outline self-start" onclick={addRule}>+ Add a rule</button>

		<div class="bg-base-200/70 rounded-box p-2.5">
			<div class="mb-2 text-[11px] font-semibold tracking-wide uppercase opacity-60">{set.rules.length ? 'Otherwise' : 'Always'}</div>
			{@render effects(set.otherwise, (fn) => edit((s) => fn(s.otherwise)))}
		</div>
		{#if serializeRules(set).length > 1000}<p class="text-error text-xs" role="alert">Too long: a component's text can be 1000 characters. Remove something.</p>{/if}
	</div>
{/if}
