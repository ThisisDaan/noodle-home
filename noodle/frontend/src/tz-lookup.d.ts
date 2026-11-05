declare module 'tz-lookup' {
	/** The IANA time zone (e.g. "Europe/Amsterdam") of a place. */
	export default function tzlookup(latitude: number, longitude: number): string;
}
