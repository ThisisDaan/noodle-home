import type { Component } from 'svelte';
import BlePanel from './BlePanel.svelte';
import HuePanel from './HuePanel.svelte';
import LocationPanel from './LocationPanel.svelte';
import NotifyPanel from './NotifyPanel.svelte';
import ThermostatPanel from './ThermostatPanel.svelte';
import type { PanelProps } from './types.ts';

/** The panels an integration can ask for with `panel = "..."` in its plugin (backend plugins/base.py). */
export const PANELS: Record<string, Component<PanelProps>> = {
	ble: BlePanel,
	hue: HuePanel,
	location: LocationPanel,
	notify: NotifyPanel,
	thermostat: ThermostatPanel
};
