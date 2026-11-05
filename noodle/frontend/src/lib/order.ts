/** The order of `siblings` after dragging `id` onto `target` (or to the end when `target` is null).
 * Dropping on a card that comes later in the list puts the dragged one after it, so two neighbours swap;
 * dropping on an earlier card puts it before. (Always "before" would leave a card that is dropped on its
 * right-hand neighbour exactly where it was.) An id that is not among the siblings (it comes from another
 * room) goes before the target. */
export function placeBefore(siblings: string[], id: string, target: string | null): string[] {
	if (target === id) return [...siblings]; // dropped on itself
	const from = siblings.indexOf(id);
	const rest = siblings.filter((x) => x !== id);
	if (target === null) return [...rest, id];
	const at = Math.max(0, rest.indexOf(target));
	const forward = from >= 0 && from <= at; // the target was after the dragged card
	rest.splice(forward ? at + 1 : at, 0, id);
	return rest;
}
