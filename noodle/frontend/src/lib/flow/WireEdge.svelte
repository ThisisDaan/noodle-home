<script lang="ts">
	import { BaseEdge, EdgeLabel, getBezierPath, useSvelteFlow, useViewport, type EdgeProps } from '@xyflow/svelte';

	let { id, selected, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, markerEnd, style, interactionWidth }: EdgeProps = $props();

	const { deleteElements } = useSvelteFlow();
	const viewport = useViewport();
	// The button lives inside the zoomed canvas; scale it back so it keeps the same size on screen (a fingertip).
	const keepSize = $derived(1 / Math.max(viewport.current.zoom, 0.1));
	const geometry = $derived(getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition }));
	const path = $derived(geometry[0]);
</script>

<!-- A wide invisible area around the wire, so a finger can hit it. -->
<BaseEdge {id} {path} {markerEnd} {style} interactionWidth={Math.max(interactionWidth ?? 0, 32)} />
<!-- Energy pulses that run along the wire while it is active (shown by CSS). -->
<path d={path} class="wire-energy" fill="none" />

{#if selected}
	<!-- The delete button sits on the middle of the selected wire, so there is no hunting for it (and no Delete key on a phone). -->
	<EdgeLabel x={geometry[1]} y={geometry[2]} transparent class="nodrag nopan">
		<button
			class="btn btn-error btn-circle shadow-lg"
			style="transform: scale({keepSize});"
			aria-label="Delete wire"
			title="Delete wire"
			onclick={(e) => { e.stopPropagation(); deleteElements({ edges: [{ id }] }); }}
		>
			✕
		</button>
	</EdgeLabel>
{/if}
