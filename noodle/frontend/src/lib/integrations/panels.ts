import type { Component } from 'svelte';
import BlePanel from './BlePanel.svelte';
import DirigeraPanel from './DirigeraPanel.svelte';
import LanPanel from './LanPanel.svelte';
import LifxPanel from './LifxPanel.svelte';
import LocationPanel from './LocationPanel.svelte';
import MatterPanel from './MatterPanel.svelte';
import NotifyPanel from './NotifyPanel.svelte';
import ZigbeePanel from './ZigbeePanel.svelte';
import type { PanelProps } from './types.ts';

/** The panels an integration can ask for with `panel = "..."` in its plugin (backend plugins/base.py). */
export const PANELS: Record<string, Component<PanelProps>> = {
	ble: BlePanel,
	dirigera: DirigeraPanel,
	lan: LanPanel,
	lifx: LifxPanel,
	location: LocationPanel,
	matter: MatterPanel,
	notify: NotifyPanel,
	zigbee: ZigbeePanel
};
