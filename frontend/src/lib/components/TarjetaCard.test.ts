// @vitest-environment jsdom
import { mount, tick, unmount } from 'svelte';
import { afterEach, expect, it } from 'vitest';
import type { DailySummaryContent } from '$lib/api';
import { digestV3View } from '$lib/digest-v3';
import TarjetaCard from './TarjetaCard.svelte';

const mounted: Record<string, unknown>[] = [];
afterEach(() => { while (mounted.length) void unmount(mounted.pop() as never); });

async function render(content: DailySummaryContent) {
  const target = document.createElement('div');
  document.body.append(target);
  mounted.push(mount(TarjetaCard, { target, props: { tarjeta: digestV3View(content)!.tarjetas[0] } }));
  await tick();
  return target;
}

it('shows ordinary measured zero and preserves an unexpected analysis note separately', async () => {
  const host = await render({ indicators_version: 1, tarjetas: [{
    titulo: 'Historia', hecho: 'Texto válido.', fuentes: ['news_rss'],
    media_diversity: { identified_outlet_count: 0 }, veracity: 'not_evaluated', confidence_note: 'Nota válida.'
  }] });
  const text = host.textContent ?? '';
  expect(text).toContain('Diversidad de medios: 0 medios identificados');
  expect(text).toContain('Veracidad no evaluada');
  expect(text).toContain('Nota del análisis: Nota válida.');
  expect(text).toContain('No respaldado');
});

it('keeps filtered compiled bullet positions and never displays the union metric', async () => {
  const metric = (count: number) => ({ media_diversity: { identified_outlet_count: count }, veracity: 'not_evaluated' });
  const host = await render({ indicators_version: 1, tarjetas: [{
    titulo: 'También hoy', notas: ['Primera', '', 'Tercera'],
    notas_indicators: [metric(1), metric(8), metric(0)], ...metric(99)
  }] });
  const bullets = [...host.querySelectorAll('li')];
  expect(bullets).toHaveLength(2);
  expect(bullets[0].textContent).toContain('1 medio identificado');
  expect(bullets[1].textContent).toContain('0 medios identificados');
  expect(host.textContent).not.toContain('99 medios');
  expect(host.textContent).not.toContain('8 medios');
});

it('leaves genuine historical cards unchanged', async () => {
  const host = await render({ tarjetas: [{ titulo: 'Antigua', hecho: 'Reseña antigua.', fuentes: ['gdelt'] }] });
  expect(host.textContent).toContain('Fuente: GDELT');
  expect(host.textContent).not.toContain('Diversidad de medios');
  expect(host.textContent).not.toContain('Veracidad');
});
