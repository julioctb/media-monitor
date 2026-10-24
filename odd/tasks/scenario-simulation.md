# scenario-simulation

**Estado:** IDEA capturada (23/oct 2026), NO diseñada ni aprobada. Origen: análisis técnico del repo MiroFish (github.com/666ghj/MiroFish, AGPL-3.0) — motor de simulación de opinión multi-agente. Este documento captura el concepto y las lecciones de ese análisis; nada está decidido ni construido.

## Objective

Módulo what-if de propagación de opinión: dado un evento hipotético («la rectora anuncia X», «crisis Y en la universidad»), simular cómo se propagaría por un ecosistema de medios y redes — alcance esperado, tono por actor, amplificadores, riesgo de escalada — ANTES de que ocurra. Convierte media-monitor de reactivo (qué pasó) a anticipatorio (qué podría pasar), sobre los datos reales ya acumulados.

## Qué se rescata de MiroFish (y qué NO)

MiroFish = wrapper sobre OASIS (camel-ai) + Zep Cloud: documento semilla → grafo de entidades → 1 agente LLM por entidad con persona generada → simulación de red social por rondas → reporte ReACT. Lo rescatable NO es el producto (sin validación empírica, cloud-lock-in con Zep, sin auth, escala real de decenas de agentes):

1. **Bucle de memoria grafo↔agentes**: cada acción de agente se reingesta como episodio y el reporteador consulta ese grafo. En media-monitor el rol del grafo lo cubre la PG existente (mentions, persons, events, tone) — SIN dependencia cloud nueva.
2. **Entrevistas post-simulación por IPC**: interrogar agentes terminada la corrida («¿por qué reaccionaste así?») — patrón de valor para explicar el informe.
3. **Simulación como subproceso aislado** del servicio API, comunicando por ficheros/cola — no bloquea workers.

**Diferenciador que MiroFish NO tiene y media-monitor sí:** media-monitor monitorea la realidad en ciclos de 15 min → puede VALIDAR la simulación contra lo que realmente pasó (menciones reales vs simuladas por actor/tono/alcance). Eso convierte el módulo en un loop medible, no en narrativa. Validación es exactamente el hueco más grande de MiroFish; no heredarlo.

## Arquitectura prevista (borrador de idea)

```
Escenario what-if (input UI) + datos reales (persons/eventos/tone histórico de PG)
    ──> generación de sociedad sintética: agentes = actores reales monitoreados
         (rectora, medios, columnistas) + arquetipos derivados del histórico
    ──> ronda 0: posts semilla = escenario + contexto del digest real
    ──> N rondas: cada agente activo decide acción vía LLM (post/repost/like/silencio)
         con tono; acciones a tabla propia simulation_actions
    ──> informe what-if: alcance por actor, tono, amplificadores, trayectoria
    ──> [fase posterior] contraste: cuando el evento real ocurre (o no),
         comparar menciones reales vs simuladas → score de la simulación
```

## Tasks tentativas (solo si se aprueba; empezar por spike)

- [ ] T0 spike desechable: loop mínimo nativo (10 agentes, 5 rondas, sin camel-oasis) sobre datos reales de un keyword activo — medir costo LLM por corrida y utilidad del output. Decidir motor DESPUÉS del spike.
- [ ] T1 modelo: tablas `simulations`, `simulation_agents`, `simulation_actions` (client-scoped, receta CRUD del repo).
- [ ] T2 motor de simulación como subproceso/proceso separado con tope de concurrencia LLM (lección MiroFish: cada agente×ronda = 1+ llamada LLM; 72 rondas×N agentes se dispara — acotar N≤30, rondas≤20 por defecto).
- [ ] T3 informe what-if (página dashboard) + entrevistas post-sim (IPC).
- [ ] T4 (fase validación) contraste simulación vs realidad + score.

## Constraints

- Módulo aislado: tablas y dominio propios; el pipeline de ingest NO se toca.
- Sin dependencias cloud nuevas ni vendor lock-in (nada estilo Zep-cloud-only).
- Nada de llamarlo «predicción» en UI: es exploración de escenarios (lección MiroFish: prometer forecasting sin validación es marketing).
- El loop de simulación se testea desde el día 1 (lección MiroFish: su núcleo de 1.600 LOC tiene 0 tests — lo crítico era lo menos testeado).
- Costo LLM con presupuesto explícito por corrida, visible en el informe.

## Open points

1. Motor: camel-oasis (pesado, trae camel-ai completo) vs loop nativo mínimo sobre la PG propia — el spike T0 responde esto.
2. Provider LLM: API actual del enriquecimiento vs inferencia local (GLM en DGX Spark disponible).
3. De dónde salen los arquetipos de agentes: ¿solo persons reales monitoreadas, o sintéticos calibrados con el histórico de tone?
4. Métrica de validación (T4): qué significa «la simulación acertó» — alcance relativo, ranking de amplificadores, tono por actor.
5. ¿Es producto para el cliente (rectoría) o herramienta interna de análisis primero?

## Route

Por definir al aprobarse. Si arranca: spike inline desechable primero, luego writer delegado backend+frontend con suites del repo (`.venv/bin/python -m pytest backend/tests -q`; `cd frontend && npm run check && npx vitest run && npm run build`).
