import { api } from './api';

export type SavedLayout = { rooms: string[]; hidden: string[]; favorites: string[]; order: string[] };

/** Dashboard layout (room order, hidden and pinned devices, tile order), stored on the hub. */
class Layout {
	rooms = $state<string[]>([]);
	hidden = $state<string[]>([]);
	favorites = $state<string[]>([]);
	order = $state<string[]>([]);
	editing = $state(false);
	saving = $state(false);
	#timer: ReturnType<typeof setTimeout> | undefined;
	#loaded = false;

	/** Take over a layout the server sends (the file was edited by hand). */
	apply(s: SavedLayout) {
		this.rooms = s.rooms;
		this.hidden = s.hidden;
		this.favorites = s.favorites;
		this.order = s.order;
	}

	async load() {
		if (this.#loaded) return;
		try {
			this.apply(await api<SavedLayout>('/layout'));
			this.#loaded = true;
		} catch {
			/* keep defaults */
		}
	}

	#save() {
		this.saving = true;
		clearTimeout(this.#timer);
		this.#timer = setTimeout(async () => {
			try {
				await api('/layout', {
					method: 'PUT',
					body: { rooms: this.rooms, hidden: this.hidden, favorites: this.favorites, order: this.order }
				});
			} finally {
				this.saving = false;
			}
		}, 400);
	}

	sorted<T extends { id: string; name: string }>(items: T[]): T[] {
		const rank = (id: string) => {
			const i = this.order.indexOf(id);
			return i < 0 ? Number.MAX_SAFE_INTEGER : i;
		};
		return [...items].sort((a, b) => rank(a.id) - rank(b.id) || a.name.localeCompare(b.name));
	}

	sortedRooms(areas: (string | null)[]): (string | null)[] {
		const rank = (a: string | null) => (a === null ? Number.MAX_SAFE_INTEGER : this.rooms.indexOf(a) < 0 ? 1e6 : this.rooms.indexOf(a));
		return [...areas].sort((a, b) => rank(a) - rank(b));
	}

	isHidden = (id: string) => this.hidden.includes(id);
	isFavorite = (id: string) => this.favorites.includes(id);

	toggleHidden(id: string) {
		this.hidden = this.isHidden(id) ? this.hidden.filter((x) => x !== id) : [...this.hidden, id];
		this.#save();
	}

	toggleFavorite(id: string) {
		this.favorites = this.isFavorite(id) ? this.favorites.filter((x) => x !== id) : [...this.favorites, id];
		this.#save();
	}

	/** Put `id` just before `beforeId` (or last), within the given sibling ids. */
	place(id: string, beforeId: string | null, siblings: string[]) {
		const ids = siblings.filter((x) => x !== id);
		const at = beforeId === null ? ids.length : Math.max(0, ids.indexOf(beforeId));
		ids.splice(at, 0, id);
		this.order = [...this.order.filter((x) => !siblings.includes(x)), ...ids];
		this.#save();
	}

	nudge(id: string, delta: number, siblings: string[]) {
		const i = siblings.indexOf(id);
		const j = i + delta;
		if (i < 0 || j < 0 || j >= siblings.length) return;
		const ids = [...siblings];
		[ids[i], ids[j]] = [ids[j], ids[i]];
		this.order = [...this.order.filter((x) => !siblings.includes(x)), ...ids];
		this.#save();
	}

	nudgeRoom(area: string, delta: number, visible: string[]) {
		const i = visible.indexOf(area);
		const j = i + delta;
		if (i < 0 || j < 0 || j >= visible.length) return;
		const rooms = [...visible];
		[rooms[i], rooms[j]] = [rooms[j], rooms[i]];
		this.rooms = rooms;
		this.#save();
	}
}

export const layout = new Layout();
export const ui = (() => {
	let selected = $state<string | null>(null);
	return {
		get selected() {
			return selected;
		},
		open(id: string) {
			selected = id;
		},
		close() {
			selected = null;
		}
	};
})();
