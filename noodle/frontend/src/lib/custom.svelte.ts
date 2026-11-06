import { api } from './api';

export type CustomField = { key?: string; label: string; type: 'switch' | 'number' | 'text'; unit?: string; min?: number | null; max?: number | null; step?: number | null };
export type CustomDevice = { id: string; name: string; fields: Required<Pick<CustomField, 'key'>> & CustomField[]; builtin: boolean };

/** The custom device being created or edited in CustomDeviceDialog. */
class CustomEditor {
	/** null = closed; { id: null } = a new one. */
	editing = $state<{ id: string | null; name: string; fields: CustomField[]; builtin: boolean } | null>(null);

	create() {
		this.editing = { id: null, name: '', fields: [{ label: '', type: 'text' }], builtin: false };
	}

	async edit(id: string) {
		const device = (await api<CustomDevice[]>('/custom')).find((d) => d.id === id);
		if (device) this.editing = { id, name: device.name, fields: device.fields.map((f) => ({ ...f })), builtin: device.builtin };
	}

	close() {
		this.editing = null;
	}
}

export const customEditor = new CustomEditor();
