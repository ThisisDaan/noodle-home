import { api } from './api';

export type Group = { id: string; name: string; members: { device_id: string; key: string }[] };

/** The light group being created or edited in GroupDialog. */
class GroupEditor {
	/** null = closed; { id: null } = a new group. */
	editing = $state<{ id: string | null; name: string; members: string[] } | null>(null);

	create() {
		this.editing = { id: null, name: '', members: [] };
	}

	async edit(id: string) {
		const group = (await api<Group[]>('/groups')).find((g) => g.id === id);
		if (group) this.editing = { id, name: group.name, members: group.members.map((m) => `${m.device_id}|${m.key}`) };
	}

	close() {
		this.editing = null;
	}
}

export const groupEditor = new GroupEditor();
