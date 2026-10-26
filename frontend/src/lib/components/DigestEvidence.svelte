<script lang="ts">
  import { formatDisplayDateTime, sourceLabel } from '$lib/format';
  import { createEvidenceContext, resolveEvidence, safeEvidenceUrl, type EvidenceContext, type EvidenceReceipt, type EvidenceRequest } from '$lib/digest-evidence';

  let { content, context, request = { field: '' } }: {
    content?: unknown;
    context?: EvidenceContext;
    request?: EvidenceRequest;
  } = $props();
  const validation = $derived(context ?? createEvidenceContext(content));
  const explanation = 'La vinculación indica procedencia registrada; no verifica la veracidad del texto ni la independencia de las publicaciones.';
  function publicationDate(value: string | null): string | null {
    return value && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value))
      ? formatDisplayDateTime(value) : value;
  }
</script>

{#snippet marker(receipt: EvidenceReceipt)}
  {#if receipt.sources.length > 0}
    <details class="digest-provenance">
      <summary>Fuentes vinculadas</summary>
      <div class="digest-provenance-material">
        <p>{explanation}</p>
        <ol>
          {#each receipt.sources as source (source.index)}
            {@const facebook = source.source.startsWith('facebook')}
            {@const href = safeEvidenceUrl(source.url)}
            {@const label = facebook ? 'Publicación de Facebook' : href && source.title ? source.title : 'Publicación registrada'}
            {@const date = publicationDate(source.published_at)}
            <li>
              <p>{#if href}<a {href} target="_blank" rel="noopener noreferrer">{label}</a>{:else}{label}{/if}</p>
              {#if !href && !facebook && source.title}<p>{source.title}</p>{/if}
              <p>{facebook ? 'Facebook' : [sourceLabel(source.source), source.outlet, source.author].filter(Boolean).join(' · ')} · Registro #{source.mention_id}</p>
              {#if date}<p>Fecha de publicación: {date} (no indica la fecha del hecho).</p>{/if}
              {#if source.summary}<p><strong>Resumen almacenado (derivado)</strong>: {source.summary}</p>{/if}
              {#if source.excerpt}<p><strong>Extracto capturado</strong>: {source.excerpt}</p>{/if}
            </li>
          {/each}
        </ol>
      </div>
    </details>
  {:else}
    <span class="digest-provenance" title="Sin referencias de procedencia válidas. Las fuentes no verifican la veracidad del texto.">No respaldado</span>
  {/if}
{/snippet}

{#await validation}
  {@render marker({ sources: [] })}
{:then catalogue}
  {@render marker(resolveEvidence(catalogue, request))}
{:catch}
  {@render marker({ sources: [] })}
{/await}

<style>
  .digest-provenance { display: block; margin-top: 0.35rem; font: 500 0.75rem/1.5 var(--font-body, sans-serif); color: inherit; }
  summary { cursor: pointer; text-decoration: underline; text-underline-offset: 0.2em; }
  summary:focus-visible, a:focus-visible { outline: 2px solid currentColor; outline-offset: 3px; }
  .digest-provenance-material { margin-top: 0.5rem; padding: 0.5rem; border: 1px solid currentColor; border-radius: var(--radius-sm, 4px); }
  .digest-provenance-material p { margin: 0.25rem 0; font: inherit; color: inherit; }
  ol { margin: 0; padding-left: 1.25rem; }
  li + li { margin-top: 0.75rem; }
  a { text-decoration: underline; }
</style>
