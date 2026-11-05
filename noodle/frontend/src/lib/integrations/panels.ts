import type { Component } from 'svelte';
import BlePanel from './BlePanel.svelte';
import LifxPanel from './LifxPanel.svelte';
import LocationPanel from './LocationPanel.svelte';
import NotifyPanel from './NotifyPanel.svelte';
import type { PanelProps } from './types.ts';

/** The panels an integration can ask for with `panel = "..."` in its plugin (backend plugins/base.py). */
export const PANELS: Record<string, Component<PanelProps>> = {
	ble: BlePanel,
	lifx: LifxPanel,
	location: LocationPanel,
	notify: NotifyPanel
};
