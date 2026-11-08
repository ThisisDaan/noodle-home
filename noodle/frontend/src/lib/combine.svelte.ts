import { api } from './api';

export type TemplateInput = { key: string; kind: 'sensor' | 'switch' | 'number'; label: string; default: number | string | null; device_class: string | null };
export type Template = { id: string; name: string; help: string; inputs: TemplateInput[] };
export type Combined = { id: string; name: string; template: string; enabled: boolean; values: Record<string, string | number> };

/** The combined device being created or edited in CombineDialog. */
class CombineEditor {
	/** null = closed; { id: null } = a new one. */
	editing = $state<{ id: string | null; template: string; name: string; values: Record<string, string | number> } | null>(null);

	create(template = 'heater') {
		this.editing = { id: null, template, name: '', values: {} };
	}

	async edit(id: string) {
		const item = (await api<Combined[]>('/combined')).find((c) => c.id === id);
		if (item) this.editing = { id, template: item.template, name: item.name, values: { ...item.values } };
	}

	close() {
		this.editing = null;
	}
}

export const combineEditor = new CombineEditor();
