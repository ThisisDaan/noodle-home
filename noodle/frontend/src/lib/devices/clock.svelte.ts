/** A clock that ticks every 30 seconds while a component is shown, so "5m ago" stays right. It only re-renders
 * the text: nothing is fetched. Use it while a component starts up and read `.now` where the text is built. */
export function useClock() {
	let now = $state(Date.now());
	$effect(() => {
		const timer = setInterval(() => (now = Date.now()), 30000);
		return () => clearInterval(timer);
	});
	return {
		get now() {
			return now;
		}
	};
}

/** "just now", "5m ago", "3h ago" for a unix time, or `none` when there is none. Pass `clock.now` to stay current. */
export function agoText(ts: number | null | undefined, now: number, none = 'no activity yet'): string {
	if (!ts) return none;
	const s = Math.max(0, Math.round(now / 1000 - ts));
	return s < 10 ? 'just now' : s < 60 ? `${s}s ago` : s < 3600 ? `${Math.round(s / 60)}m ago` : s < 86400 ? `${Math.round(s / 3600)}h ago` : `${Math.round(s / 86400)}d ago`;
}
