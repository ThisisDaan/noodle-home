<script lang="ts">
	import { api } from '../api.ts';
	import NumberOrControl from './NumberOrControl.svelte';
	import { live, type CardControl } from '../live.svelte.ts';
	import { accepts, DAY_NAMES, changeOptions, CYCLE_INPUTS, defaultChanges, pressOptions, DEFS, DEVICE_ACTIONS, actionsFor, deviceActionLabel, isNumeric } from './catalog.ts';

	let { type, data, onchange, ondelete, onduplicate, onrun, controls = [] }: {
		/** The controls of the flow's dashboard card, for the nodes that use one. */
		controls?: CardControl[];
		type: string;
		data: Record<string, any>;
		onchange: (data: Record<string, any>) => void;
		ondelete: () => void;
		onduplicate: () => void;
		onrun?: () => void;
	} = $props();

	const def = $derived(DEFS[type]);
	const set = (patch: Record<string, unknown>) => onchange({ ...data, ...patch });

	const devices = $derived(
		def?.kinds ? live.list.filter((d) => d.entities.some((e) => accepts(def, e))) : []
	);
	const entities = $derived(
		(live.devices[data.device_id]?.entities ?? []).filter((e) => accepts(def, e))
	);

	// Each kind of device gets its own actions: brightness for lights, open / close for covers, and so on.
	const allowed = $derived(actionsFor(live.devices[data.device_id]?.entities.find((e) => e.key === data.key)?.kind));
	const chosen = $derived<string[]>(data.inputs?.length ? data.inputs : [data.command ?? 'toggle']);
	// Picking another kind of device drops the actions it does not have.
	const onOff = (e?: { kind: string }) => {
		if (type !== 'action.device') return {};
		const ok = actionsFor(e?.kind);
		const left = chosen.filter((a) => ok.includes(a));
		return left.length === chosen.length ? {} : { inputs: left.length ? left : [ok[0]] };
	};

	function toggleAction(action: string, on: boolean) {
		const next = on ? [...chosen, action] : chosen.filter((a) => a !== action);
		if (next.length) set({ inputs: DEVICE_ACTIONS.filter((a) => next.includes(a)), command: undefined });
	}

	// "Device changes" and "Button pressed": every ticked option is an output on the node.
	const changes = $derived(
		type === 'trigger.event' ? pressOptions(live.devices[data.device_id], data.outputs) : changeOptions(live.devices[data.device_id])
	);
	const pressGroups = $derived(
		Object.entries(Object.groupBy(type === 'trigger.event' ? pressOptions(live.devices[data.device_id], data.outputs) : [], (o) => o.button))
	);
	function toggleChange(id: string, on: boolean) {
		const ticked: string[] = data.outputs ?? [];
		const next = on ? [...ticked, id] : ticked.filter((o) => o !== id);
		if (next.length) set({ outputs: changes.map((o) => o.id).filter((o) => next.includes(o)) });
	}

	// Motion sensors: how long the room stays "occupied" after the last motion. A setting of the sensor itself,
	// so it is saved straight away and every flow using this sensor follows it.
	const sensor = $derived(live.devices[data.device_id]);
	const usesPresence = $derived(
		sensor?.presence_minutes != null &&
			(type === 'trigger.state' ? (data.outputs ?? []).some((o: string) => o.startsWith('presence:')) : data.key === 'presence')
	);
	let presenceError = $state('');
	async function setPresence(minutes: number) {
		presenceError = '';
		try {
			await api(`/devices/${encodeURIComponent(data.device_id)}/presence`, { method: 'PUT', body: { minutes } });
		} catch (err) {
			presenceError = err instanceof Error ? err.message : String(err);
		}
	}

	// "Cycle": one JSON message per line.
	let stepsError = $state('');
	function setSteps(text: string) {
		try {
			const steps = text.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => JSON.parse(l));
			if (!steps.length || steps.some((s) => s === null || typeof s !== 'object' || Array.isArray(s))) throw new Error('need at least one {…} per line');
			stepsError = '';
			set({ steps });
		} catch (err) {
			stepsError = `Not saved: ${err instanceof Error ? err.message : err}`;
		}
	}

	function pickDevice(id: string) {
		if (type === 'trigger.state') return set({ device_id: id, outputs: defaultChanges(live.devices[id]), key: undefined });
		if (type === 'trigger.event') return set({ device_id: id, outputs: pressOptions(live.devices[id]).slice(0, 1).map((o) => o.id), keys: undefined, action: undefined });
		const first = (live.devices[id]?.entities ?? []).filter((e) => accepts(def, e));
		set({ device_id: id, key: first[0]?.key ?? '', ...(type === 'cond.state' ? { op: isNumeric(first[0]) ? 'gt' : undefined } : {}), keys: type === 'trigger.event' ? first.map((e) => e.key) : undefined, ...onOff(first[0]) });
	}

</script>

{#snippet dayPicker(emptyMeans = '')}
	<div class="flex flex-wrap gap-1">
		{#each DAY_NAMES as name, i (i)}
			{@const on = (data.days ?? []).includes(i)}
			<button type="button" class="btn btn-xs {on ? 'btn-primary' : 'btn-outline'}"
				onclick={() => set({ days: on ? (data.days ?? []).filter((x: number) => x !== i) : [...(data.days ?? []), i].sort() })}>{name}</button>
		{/each}
	</div>
	{#if emptyMeans}<p class="text-xs opacity-60">{(data.days ?? []).length ? 'Only on the days you picked.' : `None picked = ${emptyMeans.toLowerCase()}.`}</p>{/if}
{/snippet}

<div class="flex min-w-0 flex-col gap-3 text-sm break-words [&_input]:min-w-0 [&_label]:min-w-0 [&_select]:min-w-0">
	<h3 class="font-bold">{def?.label}</h3>

	{#if def?.kinds}
		<label class="floating-label">
			<span>Device</span>
			<select class="select select-sm w-full" value={data.device_id ?? ''} onchange={(e) => pickDevice(e.currentTarget.value)}>
				<option value="" disabled>Pick a device</option>
				{#each devices as d (d.id)}<option value={d.id}>{d.name}{d.area ? ` (${d.area})` : ''}</option>{/each}
			</select>
		</label>
		{#if type === 'trigger.event'}
			<fieldset class="fieldset">
				<legend class="fieldset-legend">React to</legend>
				{#each pressGroups as [button, opts] (button)}
					{#if pressGroups.length > 1}<p class="mt-1 text-xs font-semibold opacity-70">{button}</p>{/if}
					{#each opts ?? [] as o (o.id)}
						{@const ticked = (data.outputs ?? []).includes(o.id)}
						<label class="flex items-center gap-2">
							<input type="checkbox" class="checkbox checkbox-xs" checked={ticked}
								disabled={ticked && data.outputs.length === 1}
								onchange={(ev) => toggleChange(o.id, ev.currentTarget.checked)} />
							{o.short}
						</label>
					{/each}
				{:else}
					<p class="text-xs opacity-60">This device does not say which presses it sends.</p>
				{/each}
			</fieldset>
		{:else if type === 'trigger.state'}
			<fieldset class="fieldset">
				<legend class="fieldset-legend">React to</legend>
				{#each changes as o (o.id)}
					{@const ticked = (data.outputs ?? []).includes(o.id)}
					<label class="flex items-center gap-2">
						<input type="checkbox" class="checkbox checkbox-xs" checked={ticked}
							disabled={ticked && data.outputs.length === 1}
							onchange={(ev) => toggleChange(o.id, ev.currentTarget.checked)} />
						{o.label}
					</label>
				{/each}
			</fieldset>
		{:else if entities.length > 1}
			<label class="floating-label">
				<span>Entity</span>
				<select class="select select-sm w-full" value={data.key ?? ''} onchange={(e) => set({ key: e.currentTarget.value, ...onOff(entities.find((x) => x.key === e.currentTarget.value)), ...(type === 'cond.state' ? { op: isNumeric(entities.find((x) => x.key === e.currentTarget.value)) ? 'gt' : undefined } : {}) })}>
					{#each entities as e (e.key)}<option value={e.key}>{e.name} ({e.key})</option>{/each}
				</select>
			</label>
		{/if}
	{/if}

	{#if usesPresence && sensor}
		<label class="floating-label">
			<span>Clear after (min)</span>
			<input type="number" min="0.5" max="1440" step="0.5" class="input input-sm w-full" value={sensor.presence_minutes}
				onchange={(e) => setPresence(Number(e.currentTarget.value))} />
		</label>
		<p class="text-xs opacity-60">Minutes without motion before presence clears. Applies to {sensor.name} everywhere.</p>
		{#if presenceError}<p class="text-error text-xs">{presenceError}</p>{/if}
	{/if}

	{#if type === 'trigger.state'}
		<p class="text-xs opacity-60">Each ticked change becomes an output on the node; connect it to what should happen then.</p>
	{:else if type === 'trigger.event'}
		<p class="text-xs opacity-60">Each ticked press becomes an output on the node; connect it to what should happen then.
			A message's {'{count}'} is how many times it was pressed.</p>
	{:else if type === 'trigger.thermostat'}
		<div class="flex flex-wrap gap-2">
			<NumberOrControl label="Target °C" value={data.target} {controls} step={0.5} fallback={20} onchange={(v) => set({ target: v })} />
			<NumberOrControl label="Margin °C" value={data.margin} {controls} step={0.1} fallback={0.5} onchange={(v) => set({ margin: v })} />
		</div>
		<ul class="list-disc pl-4 text-xs opacity-70">
			<li><b>Too cold</b> fires once when it drops to {Number(data.target) - Number(data.margin)} °C or less.</li>
			<li><b>Warm enough</b> fires once when it reaches {Number(data.target) + Number(data.margin)} °C or more.</li>
			<li>In between nothing happens, so a heater does not keep switching on and off.</li>
		</ul>
		<p class="text-xs opacity-60">Use {'{temperature}'} in a notification to show the reading.</p>
	{:else if type === 'trigger.control'}
		<label class="floating-label"><span>Control on the card</span>
			<select class="select select-sm w-full" value={data.control ?? ''} onchange={(e) => set({ control: e.currentTarget.value })}>
				<option value="" disabled>Choose a control…</option>
				{#each controls as c (c.id)}<option value={c.id}>{c.label ?? c.id}</option>{/each}
			</select></label>
		{#if !controls.length}<p class="text-xs opacity-60">This flow has no card yet. Use <b>Dashboard card</b> above the editor to add controls.</p>{/if}
		<ul class="list-disc pl-4 text-xs opacity-70">
			<li>A switch has <b>Switched on</b> and <b>Switched off</b>; every control also has <b>Used</b>, carrying its value.</li>
		</ul>
	{:else if type === 'cond.control'}
		<label class="floating-label"><span>Control on the card</span>
			<select class="select select-sm w-full" value={data.control ?? ''} onchange={(e) => set({ control: e.currentTarget.value, value: '' })}>
				<option value="" disabled>Choose a control…</option>
				{#each controls as c (c.id)}<option value={c.id}>{c.label ?? c.id}</option>{/each}
			</select></label>
		{#if controls.find((c) => c.id === data.control)?.type === 'select'}
			<label class="floating-label"><span>Is</span>
				<select class="select select-sm w-full" value={data.value ?? ''} onchange={(e) => set({ value: e.currentTarget.value })}>
					{#each controls.find((c) => c.id === data.control)?.options ?? [] as o (o)}<option value={o}>{o}</option>{/each}
				</select></label>
		{:else if ['dial', 'slider'].includes(controls.find((c) => c.id === data.control)?.type ?? '')}
			<label class="floating-label"><span>Is exactly</span>
				<input type="number" step="any" class="input input-sm w-full" value={data.value} onchange={(e) => set({ value: Number(e.currentTarget.value) })} /></label>
		{:else if controls.find((c) => c.id === data.control)?.type === 'switch'}
			<label class="floating-label"><span>Is</span>
				<select class="select select-sm w-full" value={data.value === 'off' ? 'off' : 'on'} onchange={(e) => set({ value: e.currentTarget.value })}>
					<option value="on">On</option><option value="off">Off</option>
				</select></label>
		{/if}
		<p class="text-xs opacity-60">Goes to <b>Yes</b> when the control has that value right now, otherwise <b>No</b>.</p>
	{:else if type === 'trigger.time'}
		<label class="floating-label"><span>Time</span>
			<input type="time" class="input input-sm w-full" value={data.at} onchange={(e) => set({ at: e.currentTarget.value })} /></label>
		{@render dayPicker('Every day')}
	{:else if type === 'trigger.interval'}
		<label class="floating-label"><span>Seconds</span>
			<input type="number" min="5" class="input input-sm w-full" value={data.seconds} onchange={(e) => set({ seconds: Number(e.currentTarget.value) })} /></label>
	{:else if type === 'cond.state'}
		{#if isNumeric(live.devices[data.device_id]?.entities.find((e) => e.key === data.key))}
			<label class="floating-label"><span>Check</span>
				<select class="select select-sm w-full" value={data.op ?? 'gt'} onchange={(e) => set({ op: e.currentTarget.value })}>
					<option value="gt">greater than</option><option value="lt">less than</option><option value="eq">equals</option>
				</select>
			</label>
			<label class="floating-label"><span>Value</span>
				<input class="input input-sm w-full" value={data.value ?? ''} onchange={(e) => set({ value: e.currentTarget.value })} /></label>
		{:else}
			<p class="text-xs opacity-60">Connect each output on the node to what should happen when the device is in that state.</p>
		{/if}
	{:else if type === 'cond.for'}
		<label class="floating-label"><span>State</span>
			<select class="select select-sm w-full" value={data.state} onchange={(e) => set({ state: e.currentTarget.value })}>
				<option value="on">on / detected</option><option value="off">off / clear</option>
				<option value="above">above a value</option><option value="below">below a value</option>
			</select>
		</label>
		{#if data.state === 'above' || data.state === 'below'}
			<label class="floating-label"><span>Value</span>
				<input type="number" class="input input-sm w-full" value={data.value ?? ''} onchange={(e) => set({ value: Number(e.currentTarget.value) })} /></label>
		{/if}
		<label class="floating-label"><span>For at least (minutes)</span>
			<input type="number" min="0" class="input input-sm w-full" value={data.minutes} onchange={(e) => set({ minutes: Number(e.currentTarget.value) })} /></label>
	{:else if type === 'cond.time'}
		<div class="flex flex-wrap gap-2">
			<label class="floating-label grow"><span>From</span>
				<input type="time" class="input input-sm w-full" value={data.from} onchange={(e) => set({ from: e.currentTarget.value })} /></label>
			<label class="floating-label grow"><span>To</span>
				<input type="time" class="input input-sm w-full" value={data.to} onchange={(e) => set({ to: e.currentTarget.value })} /></label>
		</div>
	{:else if type === 'action.device'}
		<fieldset class="fieldset">
			<legend class="fieldset-legend">What can this node do? Each one you tick gets its own input on the node.</legend>
			{#each DEVICE_ACTIONS.filter((a) => allowed.includes(a)) as action (action)}
				<label class="flex items-center gap-2">
					<input type="checkbox" class="checkbox checkbox-sm" checked={chosen.includes(action)}
						disabled={chosen.length === 1 && chosen.includes(action)}
						onchange={(e) => toggleAction(action, e.currentTarget.checked)} />
					{deviceActionLabel(action, data)}
				</label>
			{/each}
		</fieldset>
		{#if chosen.includes('brightness')}
			<label class="floating-label"><span>Brightness % for "Set to"</span>
				<input type="number" min="1" max="100" class="input input-sm w-full" value={data.brightness} onchange={(e) => set({ brightness: Number(e.currentTarget.value) })} /></label>
		{/if}
		{#if chosen.includes('brighter') || chosen.includes('dimmer')}
			<label class="floating-label"><span>% per press for brighter / dimmer</span>
				<input type="number" min="1" max="50" class="input input-sm w-full" value={data.step} onchange={(e) => set({ step: Number(e.currentTarget.value) })} /></label>
		{/if}
		{#if chosen.includes('loop_start')}
			<label class="floating-label"><span>Loop through these brightness % (0 = off)</span>
				<input class="input input-sm w-full" value={(data.loop_levels ?? [25, 50, 75, 100]).join(', ')}
					onchange={(e) => set({ loop_levels: e.currentTarget.value.split(/[ ,;]+/).filter(Boolean).map((v) => Math.max(0, Math.min(100, Math.round(Number(v)) || 0))) })} /></label>
			<div class="flex flex-wrap gap-2">
				<label class="floating-label grow"><span>Seconds per step</span>
					<input type="number" min="0.2" step="0.1" class="input input-sm w-full" value={data.loop_seconds ?? 1} onchange={(e) => set({ loop_seconds: Number(e.currentTarget.value) })} /></label>
				<label class="floating-label grow"><span>Stop by itself after (s)</span>
					<input type="number" min="1" class="input input-sm w-full" value={data.loop_max_seconds ?? 60} onchange={(e) => set({ loop_max_seconds: Number(e.currentTarget.value) })} /></label>
			</div>
			<p class="text-xs opacity-70">Goes through the levels over and over. Ends on the "Stop brightness loop" input or when the time is up; the light stays at its last level.</p>
		{/if}
		{#if chosen.includes('message')}
			<p class="text-xs opacity-70">Message input understands <code>{'{"brightness": 0-100}'}</code> (0 = off), <code>{'{"on": true|false}'}</code> and <code>{'{"toggle": true}'}</code>.</p>
		{/if}
		<p class="text-xs opacity-60">Unticking an action also removes the connections to its input.</p>
	{:else if type === 'action.cycle'}
		{@const ticked = (data.inputs ?? CYCLE_INPUTS.map((i) => i.id)) as string[]}
		<label class="floating-label">
			<span>Messages, one per line (JSON)</span>
			<textarea class="textarea textarea-sm w-full font-mono" rows="5" value={(data.steps ?? []).map((s: unknown) => JSON.stringify(s)).join('\n')}
				onchange={(e) => setSteps(e.currentTarget.value)}></textarea>
		</label>
		{#if stepsError}<p class="text-error text-xs">{stepsError}</p>{/if}
		<fieldset class="fieldset">
			<legend class="fieldset-legend">Inputs. Each one you tick gets its own input on the node.</legend>
			{#each CYCLE_INPUTS as i (i.id)}
				<label class="flex items-center gap-2">
					<input type="checkbox" class="checkbox checkbox-sm" checked={ticked.includes(i.id)}
						disabled={ticked.length === 1 && ticked.includes(i.id)}
						onchange={(e) => set({ inputs: CYCLE_INPUTS.map((c) => c.id).filter((c) => (c === i.id ? e.currentTarget.checked : ticked.includes(c))) })} />
					{i.label}
				</label>
			{/each}
		</fieldset>
		<ul class="list-disc pl-4 text-xs opacity-70">
			<li>Sends the next message on. Connect it to "Control device" → "Message".</li>
			<li>A device understands <code>{'{"brightness": 50}'}</code> (0 = off), <code>{'{"on": true}'}</code> and <code>{'{"toggle": true}'}</code>.</li>
			<li><b>Next</b> / <b>Back</b>: move one step and stop at the ends.</li>
			<li><b>Loop</b>: moves forward and starts over after the last step.</li>
			<li>The position is remembered, also after a restart.</li>
		</ul>
	{:else if type === 'action.repeat'}
		<label class="floating-label"><span>Send every (seconds)</span>
			<input type="number" min="0.1" step="0.1" class="input input-sm w-full" value={data.seconds} onchange={(e) => set({ seconds: Number(e.currentTarget.value) })} /></label>
		<label class="floating-label"><span>Stop by itself after (seconds)</span>
			<input type="number" min="1" class="input input-sm w-full" value={data.max_seconds} onchange={(e) => set({ max_seconds: Number(e.currentTarget.value) })} /></label>
		<ul class="list-disc pl-4 text-xs opacity-70">
			<li><b>Start</b>: sends the message on now and then every {data.seconds}s. Start again while running does nothing.</li>
			<li><b>Stop</b>: ends it, e.g. connect "Let go after hold" to it.</li>
			<li>The safety limit stops it after {data.max_seconds}s if a stop is missed.</li>
		</ul>
	{:else if type === 'action.delay'}
		<label class="floating-label"><span>Seconds</span>
			<input type="number" min="0" class="input input-sm w-full" value={data.seconds} onchange={(e) => set({ seconds: Number(e.currentTarget.value) })} /></label>
	{:else if type === 'action.timer'}
		<NumberOrControl label="Minutes" value={data.minutes} {controls} step={0.5} fallback={5} onchange={(v) => set({ minutes: v })} />
		<label class="flex items-center gap-2">
			<input type="checkbox" class="checkbox checkbox-xs" checked={data.restart !== false} onchange={(e) => set({ restart: e.currentTarget.checked })} />
			Start again while counting = begin from {data.minutes} min again
		</label>
		<ul class="list-disc pl-4 text-xs opacity-70">
			<li><b>Start</b>: begins counting down.</li>
			<li><b>Start</b> again while counting: {data.restart === false ? 'ignored, the countdown keeps going' : `the countdown begins again from ${data.minutes} min`}.</li>
			<li><b>Stop</b>: cancels the countdown. Nothing happens after.</li>
			<li>Time is up: the flow continues to the next node.</li>
		</ul>
	{:else if type === 'action.log'}
		<label class="floating-label"><span>Message ({'{count}'} = presses)</span>
			<input class="input input-sm w-full" value={data.message} onchange={(e) => set({ message: e.currentTarget.value })} /></label>
	{:else if type === 'action.var'}
		<label class="floating-label"><span>Variable</span>
			<input class="input input-sm w-full" value={data.name} onchange={(e) => set({ name: e.currentTarget.value })} /></label>
		<label class="floating-label"><span>Value ({'{now}'} = date/time)</span>
			<input class="input input-sm w-full" value={data.value} onchange={(e) => set({ value: e.currentTarget.value })} /></label>
	{:else if type === 'cond.var'}
		<label class="floating-label"><span>Variable</span>
			<input class="input input-sm w-full" value={data.name} onchange={(e) => set({ name: e.currentTarget.value })} /></label>
		<label class="floating-label"><span>Check</span>
			<select class="select select-sm w-full" value={data.op} onchange={(e) => set({ op: e.currentTarget.value })}>
				<option value="eq">equals</option><option value="neq">is not</option>
			</select>
		</label>
		<label class="floating-label"><span>Value</span>
			<input class="input input-sm w-full" value={data.value} onchange={(e) => set({ value: e.currentTarget.value })} /></label>
	{:else if type === 'trigger.sun'}
		<label class="floating-label"><span>When</span>
			<select class="select select-sm w-full" value={data.event ?? 'sunset'} onchange={(e) => set({ event: e.currentTarget.value })}>
				<option value="sunrise">Sunrise</option><option value="sunset">Sunset</option>
			</select>
		</label>
		<label class="floating-label"><span>Minutes after (negative = before)</span>
			<input type="number" step="5" class="input input-sm w-full" value={data.offset ?? 0} onchange={(e) => set({ offset: Number(e.currentTarget.value) })} /></label>
		<p class="text-xs opacity-60">Worked out from the home's position (NOODLE_LAT / NOODLE_LON, default Amsterdam).</p>
	{:else if type === 'trigger.manual'}
		<p class="text-xs opacity-60">Runs when you press Run on the Automations page, or when another flow uses "Run another flow".</p>
	{:else if type === 'cond.day'}
		{@render dayPicker()}
	{:else if type === 'cond.dark'}
		<p class="text-xs opacity-60">Yes between sunset and sunrise, no during the day.</p>
	{:else if type === 'action.throttle'}
		<label class="floating-label"><span>Minutes</span>
			<input type="number" min="0" step="0.5" class="input input-sm w-full" value={data.minutes} onchange={(e) => set({ minutes: Number(e.currentTarget.value) })} /></label>
		<p class="text-xs opacity-60">Passes the first message on, then ignores the rest until {data.minutes} min have gone by. Stops notifications from spamming you.</p>
	{:else if type === 'action.http'}
		<label class="floating-label"><span>Address</span>
			<input class="input input-sm w-full" value={data.url} onchange={(e) => set({ url: e.currentTarget.value })} /></label>
		<label class="floating-label"><span>Method</span>
			<select class="select select-sm w-full" value={data.method ?? 'GET'} onchange={(e) => set({ method: e.currentTarget.value })}>
				<option>GET</option><option>POST</option><option>PUT</option>
			</select>
		</label>
		{#if data.method && data.method !== 'GET'}
			<label class="floating-label"><span>Body</span>
				<textarea class="textarea textarea-sm w-full font-mono" rows="3" value={data.body ?? ''} onchange={(e) => set({ body: e.currentTarget.value })}></textarea></label>
		{/if}
	{:else if type === 'action.flow'}
		<label class="floating-label"><span>Flow</span>
			<select class="select select-sm w-full" value={data.flow_id ?? ''} onchange={(e) => set({ flow_id: e.currentTarget.value })}>
				<option value="" disabled>Pick a flow</option>
				{#each (live.flows ?? []).filter((f) => f.manual) as f (f.id)}<option value={f.id}>{f.name}</option>{/each}
			</select>
		</label>
		<p class="text-xs opacity-60">Only flows with a "Run button" trigger are listed.</p>
	{:else if type === 'trigger.webhook'}
		<label class="floating-label"><span>Button name</span>
			<input class="input input-sm w-full" value={data.name} onchange={(e) => set({ name: e.currentTarget.value })} /></label>
		<p class="text-xs opacity-60">Runs when you tap a button with this name on a notification. Add that button in a "Notify" node, using the same name.</p>
	{:else if def?.fields?.length}
		<!-- A node an integration adds: its form is described by the integration (see plugins/base.py NodeField). -->
		{#each def.fields as f (f.key)}
			{#if f.type === 'select'}
				<label class="floating-label"><span>{f.label}</span>
					<select class="select select-sm w-full" value={data[f.key] ?? f.options[0]?.[0]} onchange={(e) => set({ [f.key]: e.currentTarget.value })}>
						{#each f.options as [value, label] (value)}<option {value}>{label}</option>{/each}
					</select>
				</label>
			{:else if f.type === 'textarea'}
				<label class="floating-label"><span>{f.label}</span>
					<textarea class="textarea textarea-sm w-full" rows="3" value={data[f.key] ?? ''} onchange={(e) => set({ [f.key]: e.currentTarget.value })}></textarea></label>
			{:else if f.type === 'number'}
				<label class="floating-label"><span>{f.label}</span>
					<input type="number" class="input input-sm w-full" value={data[f.key] ?? ''} onchange={(e) => set({ [f.key]: Number(e.currentTarget.value) })} /></label>
			{:else if f.type === 'buttons'}
				<fieldset class="fieldset">
					<legend class="fieldset-legend">{f.label}</legend>
					{#each data[f.key] ?? [] as b, i (i)}
						<div class="flex w-full gap-1">
							<input class="input input-xs min-w-0 grow basis-0" placeholder="Label" value={b.label}
								onchange={(e) => set({ [f.key]: data[f.key].map((x: any, j: number) => (j === i ? { ...x, label: e.currentTarget.value } : x)) })} />
							<input class="input input-xs min-w-0 grow basis-0" placeholder="Button name" value={b.hook}
								onchange={(e) => set({ [f.key]: data[f.key].map((x: any, j: number) => (j === i ? { ...x, hook: e.currentTarget.value } : x)) })} />
							<button class="btn btn-xs shrink-0" aria-label="Remove button" onclick={() => set({ [f.key]: data[f.key].filter((_: any, j: number) => j !== i) })}>✕</button>
						</div>
					{/each}
					{#if (data[f.key] ?? []).length < 3}
						<button class="btn btn-xs w-fit" onclick={() => set({ [f.key]: [...(data[f.key] ?? []), { label: '', hook: '' }] })}>+ Button</button>
					{/if}
				</fieldset>
			{:else}
				<label class="floating-label"><span>{f.label}</span>
					<input class="input input-sm w-full" value={data[f.key] ?? ''} onchange={(e) => set({ [f.key]: e.currentTarget.value })} /></label>
			{/if}
		{/each}
	{/if}

	<div class="flex flex-wrap gap-2">
		{#if onrun}<button class="btn btn-sm btn-outline" onclick={onrun}>Run from here</button>{/if}
		<button class="btn btn-sm btn-outline" onclick={onduplicate}>Duplicate <kbd class="kbd kbd-xs max-md:hidden">Ctrl D</kbd></button>
		<button class="btn btn-sm btn-error btn-outline" onclick={ondelete}>Delete node <kbd class="kbd kbd-xs max-md:hidden">Del</kbd></button>
	</div>
</div>
