<script lang="ts">
	let { name, class: cls = 'size-5' }: { name: string; class?: string } = $props();

	// 24x24 stroke icons.
	const paths: Record<string, string> = {
		home: 'M3 11l9-8 9 8M5 10v10h14V10M10 20v-6h4v6',
		devices: 'M4 5h16v10H4zM8 19h8M12 15v4',
		flow: 'M6 3v6a3 3 0 003 3h6a3 3 0 013 3v6M6 3H4m2 0h2M18 21h-2m2 0h2',
		system: 'M5 4h14v6H5zM5 14h14v6H5zM8 7h.01M8 17h.01',
		bulb: 'M9 18h6M10 21h4M12 3a6 6 0 00-3.5 10.9c.6.5 1 1.2 1 2V16h5v-.1c0-.8.4-1.5 1-2A6 6 0 0012 3z',
		plug: 'M9 3v5M15 3v5M6 8h12v3a6 6 0 01-12 0zM12 17v4',
		thermo: 'M14 14.8V5a2 2 0 00-4 0v9.8a4 4 0 104 0z',
		bluetooth: 'M7 7l10 10-5 5V2l5 5L7 17',
		motion: 'M13 4a1.5 1.5 0 110 3 1.5 1.5 0 010-3zM9 21l2-6-2-3 3-3 3 3h3M6 12l3-3',
		door: 'M6 21V4h12v17M3 21h18M14 12h.01',
		gauge: 'M12 14l4-4M4.9 19a9 9 0 1114.2 0',
		circle: 'M12 12m-3 0a3 3 0 106 0 3 3 0 10-6 0M12 12m-9 0a9 9 0 1018 0 9 9 0 10-18 0',
		star: 'M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z',
		edit: 'M4 20h4L19 9a2.8 2.8 0 00-4-4L4 16zM14 6l4 4',
		eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 12m-3 0a3 3 0 106 0 3 3 0 10-6 0',
		eyeoff: 'M3 3l18 18M10.6 6.1A9.6 9.6 0 0112 6c6 0 10 6 10 6a17 17 0 01-3.2 3.9M6.6 6.6A17 17 0 002 12s4 7 10 7a9.7 9.7 0 004.4-1M9.9 9.9a3 3 0 004.2 4.2',
		close: 'M6 6l12 12M18 6L6 18',
		check: 'M5 12l5 5L20 7',
		left: 'M15 6l-6 6 6 6',
		right: 'M9 6l6 6-6 6',
		up: 'M6 15l6-6 6 6',
		down: 'M6 9l6 6 6-6',
		dots: 'M12 5h.01M12 12h.01M12 19h.01',
		grip: 'M9 6h.01M9 12h.01M9 18h.01M15 6h.01M15 12h.01M15 18h.01',
		battery: 'M3 8h15v8H3zM21 11v2M6 11v2',
		plus: 'M12 5v14M5 12h14',
		search: 'M11 4a7 7 0 100 14 7 7 0 000-14zM21 21l-5-5',
		logout: 'M9 4H5v16h4M16 8l4 4-4 4M20 12H9',
		wifi: 'M2 9a15 15 0 0120 0M5 13a10 10 0 0114 0M8.5 16.5a5 5 0 017 0M12 20h.01',
		power: 'M12 3v9M6.4 6.4a8 8 0 1011.2 0',
		clock: 'M12 12m-9 0a9 9 0 1018 0 9 9 0 10-18 0M12 7v5l3 2',
		timer: 'M10 2h4M12 14l3-3M12 21a8 8 0 100-16 8 8 0 000 16z',
		bell: 'M6 8a6 6 0 1112 0c0 7 3 8 3 8H3s3-1 3-8M10 20a2 2 0 004 0',
		speaker: 'M4 9v6h4l5 4V5L8 9zM16 9a4 4 0 010 6M18.5 6.5a8 8 0 010 11',
		variable: 'M8 4C5 4 5 7 5 9s0 3-2 3c2 0 2 1 2 3s0 5 3 5M16 4c3 0 3 3 3 5s0 3 2 3c-2 0-2 1-2 3s0 5-3 5',
		note: 'M5 3h14v18H5zM9 8h6M9 12h6M9 16h4',
		hook: 'M10 13a5 5 0 007 0l3-3a5 5 0 00-7-7l-1 1M14 11a5 5 0 00-7 0l-3 3a5 5 0 007 7l1-1',
		bolt: 'M13 2L4 14h7l-1 8 9-12h-7z',
		branch: 'M6 3v12M6 15a3 3 0 100 6 3 3 0 000-6zM18 9a3 3 0 100-6 3 3 0 000 6zM18 9a9 9 0 01-9 9',
		pause: 'M8 5v14M16 5v14',
		sliders: 'M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0M14 4v4M8 10v4M16 16v4',
		reset: 'M4 4v6h6M4.5 14a8 8 0 100-4'
	};
</script>

<svg xmlns="http://www.w3.org/2000/svg" class={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor"
	stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
	<path d={paths[name] ?? paths.circle} />
</svg>
