// The visual view of a template: an ordered list of rules ("when ... then ..."), then "otherwise". It reads and writes the
// same template text the code box holds, so the two are one thing. A template that has more in it than this view can show
// (nested if blocks, brackets, "not") is not read (null) and stays in the code box.

export type Op = '==' | '!=' | '>' | '<' | '>=' | '<=';
export type Clause = { field: string; op: Op; value: string };
/** What a rule changes: any of these, and the text to show. */
export type Branch = { bg?: string; fill?: string; color?: string; icon?: string; hide?: boolean; text: string };
export type Rule = { join: 'and' | 'or'; clauses: Clause[]; then: Branch };
export type RuleSet = { rules: Rule[]; otherwise: Branch };

const OPS: Op[] = ['==', '!=', '>', '<', '>=', '<='];
const TAG = /\{([^{}]*)\}/g;
const CONTROL = /^(if\b|:else\b|\/if$)/;
const LEADING = /^\s*\{(?:(bg|fill|color|icon)\s+([^{}]+?)|(hide))\}[ \t]*(?:\r?\n)?/;

function parseBranch(body: string, spanColors: boolean): Branch {
	const out: Branch = { text: '' };
	let rest = body.replace(/^[ \t]*\r?\n/, '');
	for (;;) {
		const m = LEADING.exec(rest);
		if (!m) break;
		if (m[3]) out.hide = true;
		else if (m[1] === 'color' && spanColors) break; // {color x}…{/color} colours words, it is part of the text
		else out[m[1] as 'bg' | 'fill' | 'color' | 'icon'] = m[2].trim();
		rest = rest.slice(m[0].length);
	}
	out.text = rest.replace(/\r?\n[ \t]*$/, '');
	return out;
}

const quoted = (t: string) => t.length >= 2 && (t[0] === "'" || t[0] === '"') && t[t.length - 1] === t[0];

function parseCondition(src: string): { join: 'and' | 'or'; clauses: Clause[] } | null {
	const toks = src.match(/'[^']*'|"[^"]*"|>=|<=|==|!=|&&|\|\||[()<>!]|[^\s()<>!=&|'"]+/g) ?? [];
	const clauses: Clause[] = [];
	let join: 'and' | 'or' | undefined;
	let p = 0;
	for (;;) {
		const [field, op, value] = [toks[p], toks[p + 1], toks[p + 2]];
		if (field === undefined || !OPS.includes(op as Op) || value === undefined) return null;
		if (!/^[A-Za-z_][A-Za-z0-9_.]*$/.test(field) || ['not', 'and', 'or', 'true', 'false'].includes(field)) return null;
		if (['and', 'or', 'not', '&&', '||'].includes(value) || /^[()!]$/.test(value)) return null;
		clauses.push({ field, op: op as Op, value: quoted(value) ? value.slice(1, -1) : value });
		p += 3;
		if (p >= toks.length) break;
		const c = toks[p] === '&&' || toks[p] === 'and' ? 'and' : toks[p] === '||' || toks[p] === 'or' ? 'or' : undefined;
		if (!c || (join && join !== c)) return null;
		join = c;
		p++;
	}
	return { join: join ?? 'and', clauses };
}

/** The template as rules, or null when it has more in it than this view can show. */
export function parseRules(src: string): RuleSet | null {
	if (!src.trim()) return { rules: [], otherwise: { text: '' } };
	const spanColors = /\{\/color\}/.test(src);
	const tags = [...src.matchAll(TAG)].map((m) => ({ body: m[1].trim(), start: m.index!, end: m.index! + m[0].length }));
	const control = tags.filter((t) => CONTROL.test(t.body));
	if (!control.length) return { rules: [], otherwise: parseBranch(src, spanColors) };
	if (control[0].start !== src.search(/\S/) || !/^if\b/.test(control[0].body)) return null;
	const last = control[control.length - 1];
	if (last.body !== '/if' || last.end !== src.trimEnd().length) return null;
	const rules: Rule[] = [];
	let otherwise: Branch | undefined;
	if (control.slice(1).some((t) => /^if\b/.test(t.body))) return null; // an if inside the if, or a second one
	for (let i = 0; i < control.length - 1; i++) {
		const t = control[i], next = control[i + 1];
		const body = src.slice(t.end, next.start);
		if (otherwise) return null; // nothing may follow {:else}
		const cond = /^(?:if|:else\s+if)\b([\s\S]*)$/.exec(t.body);
		if (cond) {
			const c = parseCondition(cond[1]);
			if (!c) return null;
			rules.push({ ...c, then: parseBranch(body, spanColors) });
		} else if (/^:else$/.test(t.body)) otherwise = parseBranch(body, spanColors);
		else return null;
	}
	return { rules, otherwise: otherwise ?? { text: '' } };
}

const literal = (v: string) => (/^-?\d+(\.\d+)?$/.test(v) || v === 'true' || v === 'false' ? v : `'${v.replace(/['"{}]/g, '')}'`);

function branchText(b: Branch): string {
	const tags = [b.bg && `{bg ${b.bg}}`, b.fill && `{fill ${b.fill}}`, b.color && `{color ${b.color}}`, b.icon && `{icon ${b.icon}}`, b.hide && '{hide}'].filter(Boolean).join('');
	return tags + b.text;
}

/** The rules as template text. */
export function serializeRules(set: RuleSet): string {
	if (!set.rules.length) return branchText(set.otherwise);
	const parts = set.rules.map((r, i) => {
		const cond = r.clauses.map((c) => `${c.field} ${c.op} ${literal(c.value)}`).join(` ${r.join} `);
		return `{${i ? ':else ' : ''}if ${cond}}\n${branchText(r.then)}\n`;
	});
	return `${parts.join('')}{:else}\n${branchText(set.otherwise)}\n{/if}`;
}
