/** The hub's theme: one of a few ready-made ones (defined in app.css), picked on the System page for every phone and
 * computer. An empty choice is Noodle: Noodle Light or Noodle Dark, following each device's light or dark mode.
 * The list must match THEMES in the backend (config.py). */

export type ThemeOption = { id: string; label: string; dark: boolean };

export const THEMES: ThemeOption[] = [
	{ id: 'noodle-light', label: 'Noodle Light', dark: false },
	{ id: 'noodle-dark', label: 'Noodle Dark', dark: true },
	{ id: 'dracula', label: 'Dracula', dark: true },
	{ id: 'nord', label: 'Nord', dark: false },
	{ id: 'night', label: 'Night', dark: true },
	{ id: 'dim', label: 'Dim', dark: true },
	{ id: 'sunset', label: 'Sunset', dark: true },
	{ id: 'synthwave', label: 'Synthwave', dark: true },
	{ id: 'forest', label: 'Forest', dark: true },
	{ id: 'coffee', label: 'Coffee', dark: true },
	{ id: 'emerald', label: 'Emerald', dark: false },
	{ id: 'cupcake', label: 'Cupcake', dark: false },
	{ id: 'winter', label: 'Winter', dark: false },
	{ id: 'corporate', label: 'Corporate', dark: false }
];

const CACHE = 'noodle-theme';

/** A theme id this version knows, else '' (Noodle, following the device). */
export const known = (id: unknown): string => (typeof id === 'string' && THEMES.some((t) => t.id === id) ? id : '');

/** Use a theme on this page ('' for Noodle following the device), and remember it in this browser so the next load
 * starts in it before the hub has answered (app.html reads it). */
export function applyTheme(id: string, remember = true) {
	const root = document.documentElement;
	if (id) root.dataset.theme = id;
	else delete root.dataset.theme;
	// The phone's status bar takes the page colour.
	const meta = document.querySelector('meta[name="theme-color"]');
	const page = getComputedStyle(root).getPropertyValue('--color-base-200').trim();
	if (meta && page) meta.setAttribute('content', page);
	if (!remember) return;
	try {
		if (id) localStorage.setItem(CACHE, id);
		else localStorage.removeItem(CACHE);
	} catch {
		/* private window: it just starts in the default theme */
	}
}
