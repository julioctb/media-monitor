<script lang="ts">
	import DetailDialog from './DetailDialog.svelte';
	import PersonFicha from './PersonFicha.svelte';
	import { prefs, setFollowPerson } from '$lib/prefs';
	import { notifyPersist } from '$lib/toast.svelte';
	import type { PersonDetail } from '$lib/api';

	interface Props {
		/** Open request: person id, or null while the dialog is closed. */
		personId: number | null;
		onclose?: () => void;
		/** Data bridge; overridable in view tests (isolated fixtures). */
		loadFicha?: (id: number) => Promise<PersonDetail>;
	}

	/**
	 * «Ficha de identidad» — the mockup opens #detail-dialog when a directory
	 * row is clicked (data-directory-open → directoryDetail). Same chrome as
	 * Event/Mention dialogs (DetailDialog). The timeline is not in the list
	 * payload, so the ficha loads through the frontend's read-only bridge
	 * route /persons/ficha/[id] (server-to-server; the browser never calls
	 * the API directly — no CORS surface added).
	 */
	let {
		personId,
		onclose,
		loadFicha = async (id: number) => {
			const response = await fetch(`/persons/ficha/${id}`);
			if (!response.ok) throw new Error('ficha no disponible');
			return (await response.json()) as PersonDetail;
		}
	}: Props = $props();

	let detail = $state<PersonDetail | null>(null);

	$effect(() => {
		if (personId === null) {
			detail = null;
			return;
		}
		const requested = personId;
		let active = true;
		loadFicha(requested)
			.then((ficha) => {
				if (active && personId === requested) detail = ficha;
			})
			.catch(() => {
				// A failed load never leaves an empty modal open.
				if (active && personId === requested) onclose?.();
			});
		return () => {
			active = false;
		};
	});

	const followed = $derived(detail ? $prefs.persons.includes(detail.id) : false);
</script>

{#if detail && personId !== null}
	<DetailDialog
		variant="person-ficha"
		titleId="person-ficha-title"
		title="Ficha de identidad"
		open={true}
		{onclose}
	>
		<div class="dialog-body">
			<PersonFicha
				person={detail}
				{followed}
				onToggleFollow={() => {
					// $state read inside a closure needs its own narrowing.
					if (detail) notifyPersist(setFollowPerson(detail.id, !followed));
				}}
				headingTag="h2"
				headingClass="daily-dialog-title"
			/>
			<div class="dialog-actions">
				<a class="button" href={`/persons/${detail.id}`}>Abrir ficha completa</a>
			</div>
		</div>
	</DetailDialog>
{/if}
