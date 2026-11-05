<script lang="ts">
	import 'leaflet/dist/leaflet.css';
	import tzlookup from 'tz-lookup';
	import { onMount } from 'svelte';
	import type { Map as LeafletMap, Marker } from 'leaflet';

	/** Pick a place on an OpenStreetMap map: click it, drag the pin, or search for an address. The time zone
	 * follows from the place (looked up in the browser, nothing is sent anywhere for it). The map tiles and the
	 * address search come from openstreetmap.org, only while this is open; nothing here runs in the background. */
	let { latitude, longitude, onpick }: {
		latitude: number | null;
		longitude: number | null;
		onpick: (place: { latitude: number; longitude: number; timezone: string }) => void;
	} = $props();

	let el: HTMLDivElement;
	let map: LeafletMap | undefined;
	let marker: Marker | undefined;
	let L: typeof import('leaflet');

	let query = $state('');
	let results = $state<{ name: string; lat: number; lon: number }[]>([]);
	let searching = $state(false);
	let note = $state('');

	function pick(lat: number, lon: number) {
		lat = Math.round(lat * 1e5) / 1e5;
		lon = Math.round(((((lon + 180) % 360) + 360) % 360 - 180) * 1e5) / 1e5; // the map repeats around the world
		let timezone = '';
		try {
			timezone = tzlookup(lat, lon);
		} catch {
			timezone = '';
		}
		place(lat, lon);
		onpick({ latitude: lat, longitude: lon, timezone });
	}

	function place(lat: number, lon: number) {
		if (!map) return;
		if (marker) marker.setLatLng([lat, lon]);
		else {
			marker = L.marker([lat, lon], {
				draggable: true,
				icon: L.divIcon({ className: '', html: '<span class="home-pin"></span>', iconSize: [28, 28], iconAnchor: [14, 28] })
			}).addTo(map);
			marker.on('dragend', () => {
				const at = marker!.getLatLng();
				pick(at.lat, at.lng);
			});
		}
	}

	onMount(() => {
		let gone = false;
		(async () => {
			L = (await import('leaflet')).default;
			if (gone) return;
			map = L.map(el, { zoomControl: true, attributionControl: true });
			L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
				maxZoom: 19,
				attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>'
			}).addTo(map);
			if (latitude !== null && longitude !== null) {
				map.setView([latitude, longitude], 15);
				place(latitude, longitude);
			} else {
				map.setView([30, 10], 2);
			}
			map.on('click', (e) => pick(e.latlng.lat, e.latlng.lng));
			setTimeout(() => map?.invalidateSize(), 150); // the pop-up may still be opening
		})();
		return () => {
			gone = true;
			map?.remove();
		};
	});

	// A place chosen elsewhere (this device's location) moves the pin too.
	$effect(() => {
		if (map && latitude !== null && longitude !== null) {
			place(latitude, longitude);
			if (!map.getBounds().contains([latitude, longitude])) map.setView([latitude, longitude], 15);
		}
	});

	async function search(e: SubmitEvent) {
		e.preventDefault();
		if (!query.trim()) return;
		searching = true;
		note = '';
		results = [];
		try {
			const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=5&q=${encodeURIComponent(query.trim())}`);
			const rows: { display_name: string; lat: string; lon: string }[] = await res.json();
			results = rows.map((r) => ({ name: r.display_name, lat: Number(r.lat), lon: Number(r.lon) }));
			if (!results.length) note = 'Nothing found. Try a street and city, or click on the map.';
		} catch {
			note = 'Could not search (no internet?). Click on the map instead.';
		} finally {
			searching = false;
		}
	}

	function choose(r: { lat: number; lon: number }) {
		results = [];
		map?.setView([r.lat, r.lon], 17);
		pick(r.lat, r.lon);
	}
</script>

<div class="flex flex-col gap-2">
	<form class="join w-full" onsubmit={search}>
		<input class="input input-sm join-item grow" type="search" placeholder="Search for your address" bind:value={query} aria-label="Search for your address" />
		<button class="btn btn-sm join-item" disabled={searching || !query.trim()}>
			{#if searching}<span class="loading loading-spinner loading-xs"></span>{/if}Search
		</button>
	</form>
	{#if results.length}
		<ul class="bg-base-200 rounded-box flex flex-col p-1 text-sm">
			{#each results as r (r.lat + ',' + r.lon)}
				<li><button type="button" class="hover:bg-base-300 w-full truncate rounded-lg px-3 py-1.5 text-left" onclick={() => choose(r)}>{r.name}</button></li>
			{/each}
		</ul>
	{/if}
	{#if note}<p class="text-xs opacity-70">{note}</p>{/if}
	<div bind:this={el} class="rounded-box border-base-content/10 relative z-0 h-72 w-full overflow-hidden border" style="isolation: isolate"></div>
</div>

<style>
	:global(.home-pin) {
		display: block;
		width: 28px;
		height: 28px;
		border-radius: 50% 50% 50% 0;
		background: var(--color-primary, #6366f1);
		border: 3px solid white;
		box-shadow: 0 2px 6px rgba(0, 0, 0, 0.45);
		transform: rotate(-45deg);
	}
</style>
