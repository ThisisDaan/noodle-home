export type Field = { key: string; label: string; placeholder: string; secret: boolean; value: string; set: boolean | null };
export type Sensor = { address: string; name: string; model: string | null; available: boolean };

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
	error?: string | null;
	// Details of This hub (location panel)
	location_set?: boolean;
	timezone_now?: string;
	time_now?: string;
};

/** What every panel gets: the integration, and a way to hand back its new state after a change. */
export type PanelProps = { item: Integration; onchange: (updated: Integration) => void };

export const dot = (c: boolean | null) => (c === true ? 'status-success' : c === false ? 'status-error' : 'status-neutral');
