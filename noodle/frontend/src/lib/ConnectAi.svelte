<script lang="ts">
	import { api } from '#lib/api.ts';

	type Connection = { id: string; name: string; created: number };

	// How each tool takes an MCP server. `snippet` gets the hub address and the token; `where` says what to do with it.
	type Agent = { id: string; name: string; where: string; snippet: (url: string, token: string) => string };
	const json = (o: unknown) => JSON.stringify(o, null, 2);
	const AGENTS: Agent[] = [
		{ id: 'claude-code', name: 'Claude Code', where: 'Run this in a terminal:',
			snippet: (u, t) => `claude mcp add --transport http noodle ${u} --header "Authorization: Bearer ${t}"` },
		{ id: 'claude-desktop', name: 'Claude Desktop', where: 'Add this to claude_desktop_config.json (Settings → Developer → Edit Config). Needs Node.js:',
			snippet: (u, t) => json({ mcpServers: { noodle: { command: 'npx', args: ['-y', 'mcp-remote', u, '--allow-http', '--header', 'Authorization:${NOODLE_AUTH}'], env: { NOODLE_AUTH: `Bearer ${t}` } } } }) },
		{ id: 'cursor', name: 'Cursor', where: 'Save as .cursor/mcp.json in your project (or ~/.cursor/mcp.json for all projects):',
			snippet: (u, t) => json({ mcpServers: { noodle: { url: u, headers: { Authorization: `Bearer ${t}` } } } }) },
		{ id: 'vscode', name: 'VS Code', where: 'Save as .vscode/mcp.json in your project:',
			snippet: (u, t) => json({ servers: { noodle: { type: 'http', url: u, headers: { Authorization: `Bearer ${t}` } } } }) },
		{ id: 'codex', name: 'Codex', where: 'Add this to ~/.codex/config.toml:',
			snippet: (u, t) => `[mcp_servers.noodle]\nurl = "${u}"\nhttp_headers = { Authorization = "Bearer ${t}" }` },
		{ id: 'gemini', name: 'Gemini CLI', where: 'Add this to ~/.gemini/settings.json:',
			snippet: (u, t) => json({ mcpServers: { noodle: { httpUrl: u, headers: { Authorization: `Bearer ${t}` } } } }) },
		{ id: 'other', name: 'Other', where: 'Any tool that supports MCP over HTTP needs these two things:',
			snippet: (u, t) => `URL:     ${u}\nHeader:  Authorization: Bearer ${t}` }
	];

	let connections = $state<Connection[]>([]);
	let agent = $state<Agent | null>(null);
	let snippet = $state('');
	let copied = $state(false);
	let error = $state('');
	let box = $state<HTMLTextAreaElement>();

	async function load() {
		try {
			connections = await api<Connection[]>('/ai/connections');
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}

	async function pick(a: Agent) {
		agent = a;
		snippet = '';
		error = '';
		try {
			const made = await api<{ token: string; connections: Connection[] }>('/ai/connections', { body: { name: a.name } });
			connections = made.connections;
			snippet = a.snippet(`${location.origin}/mcp`, made.token);
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}

	async function copy() {
		try {
			await navigator.clipboard.writeText(snippet);
		} catch {
			box?.select(); // the clipboard API needs https; Ctrl+C works on the selection
			document.execCommand('copy');
		}
		copied = true;
		setTimeout(() => (copied = false), 2500);
	}

	async function remove(c: Connection) {
		connections = (await api<{ connections: Connection[] }>(`/ai/connections/${c.id}`, { method: 'DELETE' })).connections;
	}

	$effect(() => {
		load();
	});
</script>

{#if !agent}
	<p class="mb-3 text-sm">
		Connect an AI tool to Noodle. It can then see your devices and write automations for you. They always start switched off,
		and it cannot control your devices. Which tool do you use?
	</p>
	<div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
		{#each AGENTS as a (a.id)}
			<button class="btn btn-outline" onclick={() => pick(a)}>{a.name}</button>
		{/each}
	</div>
{:else}
	<h4 class="mb-1 font-semibold">{agent.name}</h4>
	{#if error}
		<div role="alert" class="alert alert-error alert-soft mb-2 text-sm">{error}</div>
	{:else if !snippet}
		<span class="loading loading-dots"></span>
	{:else}
		<p class="mb-2 text-sm">{agent.where}</p>
		<textarea bind:this={box} class="textarea textarea-sm mb-2 h-32 w-full font-mono text-xs" readonly value={snippet}></textarea>
		<div class="flex flex-wrap items-center gap-2">
			<button class="btn btn-sm btn-primary" onclick={copy}>{copied ? 'Copied' : 'Copy'}</button>
			<span class="text-xs opacity-60">The key is shown only now. Then try: "Make a Noodle automation that turns on the hallway light at sunset."</span>
		</div>
	{/if}
	<button class="btn btn-sm btn-ghost mt-3" onclick={() => (agent = null)}>← Other tools</button>
{/if}

{#if connections.length}
	<div class="mt-5">
		<p class="mb-1 text-sm font-semibold">Connected</p>
		<ul class="divide-base-300 divide-y text-sm">
			{#each connections as c (c.id)}
				<li class="flex items-center justify-between py-1.5">
					<span>{c.name} <span class="text-xs opacity-60">· {new Date(c.created * 1000).toLocaleDateString()}</span></span>
					<button class="btn btn-xs btn-ghost text-error" onclick={() => remove(c)}>Disconnect</button>
				</li>
			{/each}
		</ul>
	</div>
{/if}
