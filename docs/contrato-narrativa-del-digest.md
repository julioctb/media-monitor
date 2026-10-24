# El contrato de la narrativa del digest: del `if` defensivo al schema

Decision de diseño para `backend/app/summaries/digest.py` → `apply_narrative`.
La escena completa: `build_daily_summary` (builder.py) genera los facts
deterministas, le pide la narrativa al LLM y funde la respuesta sobre los
facts. Este documento explica el contrato y por qué se migra a modelos
Pydantic.

## 1. Las capas (intactas, no se tocan)

    facts (determinista) → narrativa (LLM) → merge → validate_digest

El LLM **no es la fuente de verdad**: narra sobre datos que ya existen. El
merge (`apply_narrative`) nunca reescribe secciones deterministas; solo
completa campos de prosa (`summary`, `why_it_matters`, `tone`, `watch`,
`activity`, `agenda`, `redes`).

## 2. El problema: portero sin libro de novedades

Hasta ahora cada campo se defendia con `isinstance` dispersos y `continue`
silenciosos. Consecuencias:

- **Contrato invisible**: la forma esperada del payload vivia en un docstring
  y en veinte `if` repartidos. Para saber que se le pide al modelo había que
  leer la funcion entera.
- **Fallos mudos**: un entry malformado (`index` como texto, `when` vacio,
  nota en campo equivocado) se descartaba sin rastro. El digest salia con la
  seccion vacia y `errors == []` — el builder lo aceptaba como modo `llm`.
  Depurar era reconstruir a mano que le llego al modelo.
- **Costo de mantenimiento**: cada campo nuevo = otro bloque de defensa
  copypasteada.

## 3. La mejora: un solo contrato, declarado

Los modelos Pydantic (`digest_schema.py`) declaran la forma del payload una
unica vez. `apply_narrative` los usa para validar entrada por entrada:

- **Entry valido** → se aplica (igual que hoy).
- **Entry malformado** → se descarta (igual que hoy) **pero queda registrado
  en el log con su ruta y razon**: `items[2]: index debia ser entero`.
  El misterio del dato que no aparece termina.
- **Seccion con shape fatal** (p.ej. `items` no es lista) → sigue siendo
  error de `apply_narrative`, igual que hoy.

Garantias de comportamiento que NO cambian (pinneadas en
`tests/test_summaries.py`):

- Tolerancia por entry: un entry malo no tira la narrativa entera.
- Contenedores legacy: filas pre-v2 sin las keys nuevas no se fabrican ni
  rompen.
- Los facts deterministas jamas se reescriben.
- `strict=True` en los modelos: sin coercion implicita (hoy `"2"` como
  index se descarta; asi sigue siendo — pydantic lax lo aceptaria y seria
  un cambio de contrato silencioso).

## 4. Paso siguiente: `response_format` (pendiente)

El mismo schema exporta su json schema (`Model.model_json_schema()`). Cuando
el server de inference lo soporte bien, el builder puede pedirle al LLM
generar contra esa planilla (`response_format: json_schema`) en vez de
confinarse a `json_object`. Menos respuestas descartadas. La validar
post-proceso de `apply_narrative` se mantiene igual: corrobora, no confia.

## 5. Que NO se hace

- No se divide la narrativa en una llamada por seccion (mas llamadas, menos
  coherencia editorial, mas complejidad de orquestacion).
- No se abstrae mas el core determinista: ya esta factorizado y es el activo.
