<script lang="ts">
	import PersonFicha from '$lib/components/PersonFicha.svelte';
	import { prefs, seedPrefsFromServer, setFollowPerson } from '$lib/prefs';
	import { notifyPersist } from '$lib/toast.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	// Same mm_prefs seed as the list: the «Seguir persona» button renders its
	// real state on first paint (hydration matches SSR).
	// svelte-ignore state_referenced_locally
	seedPrefsFromServer(data.prefs);

	const person = $derived(data.person);
	const followed = $derived($prefs.persons.includes(person.id));
</script>

<svelte:head>
	<title>{person.name} | Media Monitor</title>
</svelte:head>

<a href="/persons" class="text-sm font-medium text-muted transition-colors hover:text-ink">
	← Volver a personajes
</a>

<PersonFicha
	{person}
	{followed}
	onToggleFollow={() => notifyPersist(setFollowPerson(person.id, !followed))}
/>

<p class="directory-disclaimer">
	Los recuentos corresponden al histórico completo del cliente; el timeline refleja las menciones
	vinculadas al personaje durante el enriquecimiento.
</p>
