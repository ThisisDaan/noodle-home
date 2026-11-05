export type Field = { key: string; label: string; placeholder: string; secret: boolean; hidden?: boolean; help?: string; advanced?: boolean; value: string; set: boolean | null };
export type Sensor = { address: string; name: string; model: string | null; available: boolean };
export type LanDevice = { key: string; name: string; address: string; available: boolean };
export type Bulb = { mac: string; name: string; address: string; available: boolean };

/** One thing a search found (backend discovery.py). */
export type Found = { key: string; name: string; detail?: string; added: boolean };
/** A search for new devices: it runs only when the user starts it, and the server pushes what it finds. */
export type SearchState = {
	searching: boolean;
	/** Seconds left when the server sent this, and the length of the whole search. */
	remaining: number;
	total: number;
	found: Found[];
	error: string | null;
};

/** One entry of the Integrations page, as the server describes it (see backend integrations.py). */
export type Integration = {
	id: string;
	name: string;
	help: string;
	icon: string;
	/** A component from panels.ts shown with the settings. */
	panel: string | null;
	/** The panel replaces the settings form and the help text. */
	custom_form: boolean;
	connected: boolean | null;
	added: boolean;
	always: boolean;
	fields: Field[];
	// Details some integrations add (Bluetooth)
	sensors?: Sensor[];
	bulbs?: Bulb[];
	devices?: LanDevice[];
	add_hint?: string;
	// IKEA DIRIGERA pairing
	paired?: boolean;
	address?: string;
	searchable?: boolean;
	/** What a search looks for ("Hue bridges"), what to do on the device meanwhile, and the button to press. */
	noun?: string;
	search_hint?: string;
	press_hint?: string;
	search?: SearchState;
	error?: string | null;
	// Details of This hub (location panel)
	location_set?: boolean;
	timezone_now?: string;
	time_now?: string;
};

/** What every panel gets: the integration, and a way to hand back its new state after a change. */
export type PanelProps = { item: Integration; onchange: (updated: Integration) => void };

export const dot = (c: boolean | null) => (c === true ? 'status-success' : c === false ? 'status-error' : 'status-neutral');
