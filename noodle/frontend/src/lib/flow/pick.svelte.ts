/** "Add the next step": set by the + next to a node's output, read by the editor page (nodes are drawn by the
 * canvas library, so they cannot be handed a callback). */
export const pick = $state<{ from: { id: string; handle: string } | null }>({ from: null });
