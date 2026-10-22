/** Hosts whose URLs normalize to a page ref (tokenless FB ingest). */
const FB_HOST_RE = /^(?:(?:www|m|mbasic|web)\.)?facebook\.com$/;

const NUMERIC_RE = /^\d+$/;

/**
 * Reduce a pasted Facebook URL — or bare slug/id — to the page ref the
 * tokenless ingest adapter builds `facebook.com/<ref>` from: public slug,
 * numeric id or `groups/<id>`. Accepts permalink paths (`/posts/..`),
 * querystrings, trailing slashes and `profile.php?id=`; foreign domains
 * and empty input return null.
 */
export function normalizeFacebookPageRef(raw: string): string | null {
	const value = raw.trim();
	if (value === '') return null;

	let path = value;
	const withHost = /^(?:https?:\/\/)?([^/?#]+\.[^/?#]+)(\/[^#]*)?$/.exec(value);
	if (withHost) {
		if (!FB_HOST_RE.test(withHost[1].toLowerCase())) return null;
		path = withHost[2] ?? '';
	}

	const [pathPart, query = ''] = path.split('#')[0].split('?');
	const segments = pathPart.split('/').filter(Boolean);
	const head = segments[0]?.toLowerCase();

	if (head === 'profile.php') {
		const id = new URLSearchParams(query).get('id');
		return id !== null && NUMERIC_RE.test(id) ? id : null;
	}
	if (head === 'groups') {
		return segments[1] !== undefined && NUMERIC_RE.test(segments[1])
			? `groups/${segments[1]}`
			: null;
	}
	return segments.length > 0 ? segments[0] : null;
}
