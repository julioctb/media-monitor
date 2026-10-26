// @vitest-environment jsdom
import { mount, tick, unmount } from 'svelte';
import { afterEach, expect, it } from 'vitest';
import BriefPanel from './BriefPanel.svelte';
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
