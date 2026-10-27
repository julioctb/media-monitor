// @vitest-environment jsdom
import { mount, tick, unmount } from 'svelte';
import { afterEach, expect, it } from 'vitest';
import BriefPanel from './BriefPanel.svelte';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
const mounted: ReturnType<typeof mount>[] = [];
afterEach(async () => { for (const instance of mounted.splice(0)) await unmount(instance); document.body.replaceChildren(); });
it('keeps legacy vigilancia and afectacion prose explicitly unbacked', async () => {
  const host = document.createElement('div'); document.body.append(host);
  mounted.push(mount(BriefPanel, { target: host, props: {
    riesgos: [{ titulo: 'Riesgo', razon: null, afectacion: 'Trayectoria: presión creciente' }],
    vigilancia: [{ persona: 'Sujeto bajo seguimiento', nota: 'Lectura de vigilancia', fecha: '', afectacion: null }]
  } }));
  await tick();
  const risk = [...host.querySelectorAll('.digest-brief-block')].find(block => block.querySelector('h3')?.textContent === 'Riesgo')!;
  const vigilance = [...host.querySelectorAll('.digest-brief-block')].find(block => block.querySelector('h3')?.textContent === 'Vigilancia')!;
  expect(risk.textContent).toContain('Trayectoria: presión creciente');
  expect(risk.textContent).toContain('No respaldado');
  expect(vigilance.textContent).toContain('Lectura de vigilancia');
  expect(vigilance.textContent).toContain('No respaldado');
});

it('renders independent optional attention paragraphs without hiding unsupported or HTML-like prose', async () => {
  const host = document.createElement('div'); document.body.append(host);
  mounted.push(mount(BriefPanel, { target: host, props: {
    decisiones: [{ titulo: 'Consulta', razon: 'Lectura política', afectacion: null,
      accionSugerida: 'Verificar á <script>no ejecutar</script> https://fuente.test/á',
      condicion: 'Contar con el acta original' }]
  } }));
  await tick();
  const paragraphs = [...host.querySelectorAll('.digest-brief-attention')];
  expect(paragraphs).toHaveLength(2);
  expect(paragraphs[0].textContent).toContain('Acción sugerida: Verificar á <script>no ejecutar</script> https://fuente.test/á');
  expect(paragraphs[1].textContent).toContain('Condición: Contar con el acta original');
  for (const paragraph of paragraphs) expect(paragraph.textContent).toContain('No respaldado');
  expect(host.querySelector('script')).toBeNull();
  expect(host.querySelector('a')).toBeNull();
});

it('wraps legitimate unbroken attention text in its owning paragraph without truncation', async () => {
  const host = document.createElement('div'); document.body.append(host);
  const text = `Verificar https://fuente.test/${'á'.repeat(300)}`;
  const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'BriefPanel.svelte'), 'utf8');
  const stylesheet = document.createElement('style');
  stylesheet.textContent = source.match(/<style>([\s\S]*?)<\/style>/)?.[1] ?? '';
  document.head.append(stylesheet);
  try {
    mounted.push(mount(BriefPanel, { target: host, props: { decisiones: [{ titulo: 'Consulta', razon: null, afectacion: null, accionSugerida: text }] } }));
    await tick();
    const paragraph = host.querySelector('.digest-brief-attention')!;
    expect(paragraph.textContent).toContain(text);
    expect(getComputedStyle(paragraph).overflowWrap).toBe('anywhere');
  } finally { stylesheet.remove(); }
});
