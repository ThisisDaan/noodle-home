import { api } from '../api.ts';
import { registerNodes, type NodeSpec } from './catalog.ts';

/** The flow nodes integrations add, fetched once and added to the catalog. */
class PluginNodes {
	/** Goes up when nodes were added, so lists built from the catalog update. */
	version = $state(0);
	#loading: Promise<void> | undefined;

	ensure(): Promise<void> {
		this.#loading ??= api<NodeSpec[]>('/flow/nodes')
			.then((specs) => {
				registerNodes(specs);
				this.version++;
			})
			.catch(() => {
				this.#loading = undefined;
			});
		return this.#loading;
	}
}

export const pluginNodes = new PluginNodes();
