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

## 4. `response_format` (implementado)

`digest_schema.narrative_response_schema()` exporta el JSON Schema que
`builder._openai_generator` envía en el primer intento como
`response_format: json_schema`. Los reintentos usan JSON simple para
proveedores sin soporte de generación guiada. La validación posterior de
`apply_narrative` se conserva: cumplir el schema no acredita veracidad ni
correspondencia factual entre una reseña y su noticia.

## 5. Que NO se hace

- No se divide la narrativa en una llamada por seccion (mas llamadas, menos
  coherencia editorial, mas complejidad de orquestacion).
- No se abstrae mas el core determinista: ya esta factorizado y es el activo.

## 6. Contrato editorial y persona principal bajo seguimiento

**Contrato objetivo:** la voz integral de asesoría y la trazabilidad por
aseveración dependen de las fases posteriores de
`odd/tasks/political-analysis-traceability.md`. Documentarlas no significa
que estén implementadas, ni que los datos recibidos estén verificados.

### Identidad, búsqueda y lectura

`digest_focus_person_id` identifica a la **persona principal bajo
seguimiento**, no necesariamente a quien lee el informe. Las palabras
clave recuperan noticias y contexto; `Person` conserva identidad, cargo,
institución y variantes. La watchlist identifica personas adicionales bajo
vigilancia. Ninguno de esos conceptos debe sustituirse por otro.

Para seguir a otra personalidad se cambia la configuración y las búsquedas,
no el código ni nombres dentro del prompt. Una noticia institucional puede
ser pertinente aunque no mencione literalmente a la persona principal.
La falta de mención tampoco acredita participación, responsabilidad o
perjuicio: la relación debe explicarse o declararse no establecida.

### Voz y separación de niveles

El lector recibe criterio político: actores, posiciones documentadas,
gobernabilidad, legitimidad, negociación, costos reputacionales y margen de
maniobra cuando la evidencia permita esa lectura. El informe puede ser
incómodo para la persona seguida y su equipo; no es un alegato a su favor.
No atribuir intenciones privadas, apoyo público ni facultades a partir de
una cobertura favorable o de un cargo. Un candidato no tiene por ello las
atribuciones de una autoridad en ejercicio.

Distinguir siempre tres niveles:

1. **Hecho reportado:** quién afirma qué, cuándo y con qué respaldo.
2. **Lectura política:** interpretación y mecanismo que la sostiene, con
   sus límites; los escenarios son posibilidades, no hechos ocurridos.
3. **Atención recomendada:** qué verificar, coordinar o resolver, bajo qué
   condición y con qué plazo documentado, si existe.

Estas capas son editoriales. La fase 1 no añade campos de respuesta ni
componentes de presentación para renderizarlas.

### Categorías objetivo y ejemplos de aceptación

| Categoría | Requiere | No se demuestra con |
|---|---|---|
| Riesgo | Consecuencia adversa plausible vinculada a la persona seguida | Tono negativo o mera mención |
| Decisión / atención | Necesidad concreta de verificar, coordinar, fijar postura o resolver | Cantidad de publicaciones |
| A favor | Desarrollo favorable sustentado y pertinente | Suponer respaldo ciudadano |
| Ruido | Baja relevancia decisional explicada | Incomodidad o un solo origen |
| Vigilancia | Señal pertinente sobre una persona configurada | Atribuirle todo el tono de la noticia |

Mantener la regla de tres cuando existan tres candidatas sustantivas. Los
pisos deterministas actuales se revisarán en fases posteriores; este
contrato no afirma que ya distingan todas estas dimensiones.

| Entrada sintética | Lectura aceptable | No afirmar |
|---|---|---|
| Denuncia de gasto irregular, sin contraste documental | Frente de escrutinio que requiere verificar la documentación | Desvío demostrado |
| Consulta aplazada, sin nueva fecha ni acuerdo | Margen para negociar e incertidumbre sobre el proceso | Conflicto resuelto |
| Aniversario reproducido por siete medios | Visibilidad institucional, sin decisión pendiente documentada | Urgencia por volumen |
| Vencimiento próximo en una nota neutral | Atención por el plazo acreditado | Ausencia de riesgo por tono |
| Denuncia grave con un solo origen | Gravedad potencial separada de corroboración insuficiente | Ruido por tener una fuente |
| Candidato mencionado en un asunto municipal | Pertinencia para su posición pública, sin mando gubernamental | Ordenar a la policía |

### Ejemplo sintético de asesoría

**Hecho reportado:** una publicación informa el aplazamiento de una consulta,
sin nueva fecha ni acuerdo entre las partes.

**Lectura política:** el aplazamiento abre margen para negociar, pero
prolonga la incertidumbre sobre la conducción del proceso. Si el siguiente
paso no se aclara, la discusión puede desplazarse del contenido de la
propuesta a su legitimidad.

**Atención recomendada:** confirmar el alcance del aplazamiento y las
condiciones de participación antes de comunicar otro calendario.

**Límite:** no se acredita resolución del desacuerdo ni una nueva fecha.
La posible disputa de legitimidad es una interpretación condicionada.

Sobre una movilización universitaria reportada, la lectura para una rectoría
puede examinar continuidad académica e interlocución; para un gobernante,
coordinación y efectos documentados en servicios dentro de su competencia;
para un candidato, pertinencia de su posición pública y verificación previa.
No adjudicarle al candidato capacidad de ejecución gubernamental. Estos
son ejemplos de revisión humana, no resultados demostrados por un
proveedor real ni por un generador falso de pruebas.

### Entrada del narrador: persona principal

La fase 1 resuelve el foco con `queries.get_client_person` y el `client_id`
efectivo. La entrada opcional del narrador contiene únicamente:

```json
{"focus_person": {"name": "Nombre registrado", "role": null, "org": null}}
```

Se usa cargo e institución registrados cuando existen; `null` significa
información desconocida. El bloque no identifica al lector ni presupone
que la persona participe en cada noticia. Puede existir aunque no haya
menciones suyas en el corte. Si el ID falta, no existe o pertenece a otro
cliente, se omite sin elegir otra persona por volumen o por watchlist.

El contexto vive solo en el prompt: no amplía `DailySummary.content`, el
schema de respuesta ni las revisiones almacenadas. Las llamadas existentes
sin foco conservan su proyección y mensaje. Las pruebas con generador falso
acreditan este transporte y sus límites, no calidad editorial, facultades
legales ni verdad factual. El reemplazo integral del prompt es posterior.

### Configuración persistida única

En Configuración → Operación, «Persona principal bajo seguimiento» usa el
setting existente `digest_focus_person_id`. Elegir otra persona y guardar
cambia el contexto de futuras generaciones; no cambia automáticamente las
keywords, la watchlist ni resúmenes históricos. Elegir «Sin persona
principal» permite conservar un resumen general sin inventar otro foco.

Si la persona guardada no está en el catálogo cargado, una opción explícita
conserva su ID hasta que el operador decida cambiarlo. El antiguo foco local
de palabras clave ya no compite con esta selección; no se convierte texto
de localStorage en identidad ni se modifica el valor persistido por ello.
Para una personalidad aún no identificada se pueden configurar keywords y
seleccionar después su perfil registrado; no existe un alta manual nueva
ni una inferencia automática del sujeto principal en esta fase.

## 7. Identidad de historias: una sola autoridad

La construcción del digest no vuelve a agrupar por similitud de titulares
los eventos que ingestión mantuvo separados. Tampoco combina publicaciones
sueltas mediante cadenas de coincidencias. La limpieza visual de títulos
continúa, pero no decide identidad ni suma entre eventos su tono, personas
o reiteración. La cobertura conserva todas las publicaciones del corte.

El contador histórico de historias fundidas se mantiene compatible como
cero cuando aparece junto a otros descartes; sin descartes no se fabrica
un bloque vacío. Las cosméticas siguen excluyéndose de tarjetas sin dejar
de contar para cobertura. Puede haber historias parecidas con IDs distintos
hasta que el mecanismo de identidad de ingestión las resuelva: se prefiere
esa duplicación conservadora a mezclar asuntos diferentes.

Esto no reconstruye eventos históricos ni regenera informes almacenados.
El material local al corte y la procedencia de la prosa se endurecen en
las siguientes unidades de la fase 2.

### Portadas históricas y entradas de comparación

Las portadas agregadas que sobrevivieron en eventos antiguos no participan
en la comparación de identidad: se excluyen del conjunto histórico de
títulos y del título canónico usado para puntuar. El mismo filtro protege
las dos direcciones del comparador compartido con el árbitro y las
herramientas de mantenimiento. Los umbrales y la recuperación por variantes
legítimas de un título se conservan.

Esta protección se aplica al procesamiento futuro; no borra las portadas
almacenadas, no cambia sus enlaces históricos y no ejecuta reparaciones.
Las pruebas de mantenimiento operan exclusivamente sobre SQLite en memoria.

### Material de cada corte

El título y la reseña de una historia proceden de la misma publicación
elegible del corte: se priorizan medios y, después, la fecha de publicación
más reciente y el ID como desempate. Las fechas SQLite sin zona se
interpretan como UTC para compararlas de forma consistente.

El resumen global del evento no sustituye el material del corte. Las
portadas agregadas no representan historias, aunque siguen contando para
cobertura y conservan sus entradas cuando forman parte de un inventario de
fuentes adjunto. Si un grupo solo contiene portadas, no produce una noticia.
La publicación elegida no demuestra por sí sola que todas las notas de un
evento histórico mal agrupado traten del mismo asunto; no se ha ejecutado
una reconstrucción histórica.

### Recuperación de prosa tras un fallo

Un fallo u omisión de generación solo permite recuperar la prosa anterior
si el corte completo conserva las mismas publicaciones, agrupadas en las
mismas historias. La comparación usa canal, URL y título de publicación;
no depende del orden de presentación ni de compartir un ID de evento.
Si cambia o falta identidad, se conserva la plantilla del corte actual,
no el titular, agenda, redes o reseña antiguos.

La recuperación del mismo corte conserva la prosa y sus revisiones. Es una
comprobación de identidad de publicaciones, no de texto externo inmutable
ni de verdad. Cuando publicaciones de cobertura no aparecen en las fuentes
almacenadas, no se presupone completitud: la recuperación falla de forma
conservadora. El catálogo congelado y las etiquetas explícitas de falta de
respaldo corresponden a la siguiente unidad de evidencia.

## 8. Catálogo de publicaciones congelado

Cada nuevo corte incorpora `evidence.version = 1` y su catálogo `sources`,
obtenido de las mismas publicaciones del cliente y ventana. Los índices
empiezan en cero y siguen el ID de publicación, no el orden visual de las
historias. `source_refs` identifica los miembros no agregados de una noticia;
`material_ref` identifica su publicación representativa.

El catálogo conserva URL, medio, autor, fecha UTC, título y material limitado:
`summary` es el resumen derivado almacenado; `excerpt` procede de
`Mention.content`. Ambos se acotan por separado a 300 caracteres y no se
sustituyen entre sí. El catálogo incluye también la cobertura que no produce
una historia. No contiene una certificación de verdad ni atribuye por sí solo
la prosa generada a esas fuentes. La vinculación de texto y etiquetas se
implementa en la siguiente unidad.

### Entrada del modelo

La proyección de entrada versión 1 lee el material de ese catálogo, no las
reseñas mutables del informe. Omite IDs de base de datos y URLs; mantiene
índices de fuente, texto acotado, conteos y contexto registrado de personas.
El material se trata como dato no confiable, no como instrucciones.

Un catálogo explícito mal formado o de versión desconocida no habilita una
ruta alternativa de texto mutable. La ausencia del catálogo conserva la
compatibilidad de las llamadas antiguas. La salida del modelo no puede
reescribir el catálogo ni la pertenencia de fuentes de una historia.

### Transporte a tarjetas y compilados

Las tarjetas conservan la pertenencia de fuentes y la referencia de su
material. Un compilado conserva la unión de fuentes y `notas_refs` alineado
con cada viñeta; no se le inventa una única publicación representativa.
Estos índices transportan entrada documental, no respaldo de cada afirmación.

## 9. Procedencia por campo sin descartar prosa válida

La salida admite `references`, un mapa opcional de rutas exactas a índices
del catálogo. Los índices de noticia son semánticos; las posiciones de otras
listas son las originales antes de omitir entradas inválidas.

| Ruta | Texto vinculado |
| --- | --- |
| `headline` | Lectura principal |
| `items.<index>.summary`, `.why_it_matters`, `.confidence_note`, `.angulo_nuevo` | Campos de noticia |
| `seleccion.<index>.razon` | Motivo de selección |
| `agenda.<position>.when`, `.title`, `.status`, `.source` | Campos de agenda |
| `redes.<channel>.note` | Nota del canal |
| `redes.<channel>.cuentas.<position>.cuenta`, `.nota` | Seguimiento por cuenta |
| `personas.<position>.fact` | Reseña de persona registrada |

Cero es un índice válido; booleanos, cadenas numéricas, índices ajenos al
campo o fuera del catálogo invalidan el conjunto de referencias, NO su texto
estructuralmente válido. No se inventa una cita porque la historia tenga
publicaciones. La validación de los demás campos e índices sigue siendo
estricta.

El backend crea `provenance.<field>` con texto exacto, referencias, origen,
estado `linked`/`unbacked` y huella del catálogo validado. `linked` significa
procedencia registrada: no verifica verdad, causalidad ni corroboración
independiente. La lectura vuelve a comprobar texto, huella y ámbito; no
confía solo en el estado guardado. Los compilados conservan una vinculación
por viñeta y requieren todos los padres documentales de su transformación.

La recuperación de prosa añade igualdad del material congelado a los
controles de identidad del corte. Un mismo evento o URL no autoriza copiar
análisis de material cambiado o desconocido. Una respuesta rechazada no
filtra texto parcialmente aplicado a la plantilla. Las etiquetas visibles
en interfaz y exportación se implementan en T9.

### Restauración de revisiones

Las revisiones no guardan un catálogo de evidencia. Restaurar una revisión
invalida la procedencia del titular, incluso si su texto coincide con el
actual. Se conservan el catálogo y los metadatos de las tarjetas actuales;
no se adjudican al titular restaurado. Se sincronizan el titular del brief
y el texto exportable con la narrativa elegida. La invalidación se asigna
como un nuevo JSON y se confirma en base de datos para sobrevivir a la
siguiente lectura. No se reconstruyen ni migran revisiones históricas.

## 10. Exportación legible con las mismas advertencias

El texto exportable vuelve a resolver cada vinculación contra texto, catálogo
y ámbito. Conserva la prosa sin referencia con «No respaldado» o «No
respaldada»; las referencias válidas aparecen como `Fuentes vinculadas: #0`.
El registro final enumera solo las publicaciones efectivamente citadas en esa
salida, no todo el conjunto recuperado. Distingue resumen derivado y extracto
capturado, y rotula la fecha como fecha de publicación, no del hecho.

El exportador incluye el bucket de riesgos ya existente y presenta el delta
tipado como texto, sin volcar diccionarios de Python ni perder filas antiguas
de texto. Las fechas derivadas sin vinculación también conservan su advertencia.
Esto no cambia la clasificación de riesgos, los pisos ni las reglas temporales;
esas decisiones analíticas corresponden a T5/T6/T8.

## 11. Validación del catálogo en la interfaz

El lector de procedencia recalcula SHA-256 sobre los campos conocidos del
catálogo congelado; no confía en una huella declarada por el contenido. Compara
el texto original antes de limpiarlo para presentación y exige referencias
enteras válidas dentro del ámbito de cada campo o viñeta compilada.

La validación usa Web Crypto integrado, disponible en localhost o HTTPS.
Mientras está pendiente o no está disponible, el estado permanece no respaldado;
no se activa por la mera presencia de enlaces ni por pertenecer a una historia.
Los enlaces requieren HTTP(S) absoluto, sin reparar valores malformados ni
aceptar credenciales en la URL. El lector no consulta APIs ni comparte caché
mutable entre informes o clientes.

## 12. Inspector compartido de publicaciones

«Fuentes vinculadas» abre un desplegable nativo con las publicaciones de ese
campo, no con todo el catálogo. Muestra identidad del registro, enlace seguro,
fecha de publicación y, cuando existen, resumen derivado y extracto capturado.
La atribución de Facebook mantiene el rótulo genérico sin presentar nombres de
páginas o grupos. Un enlace inválido queda como texto, nunca como ancla reparada.

La explicación visible aclara que procedencia no equivale a veracidad ni a
independencia entre publicaciones. Los estados sin referencias válidas conservan
la prosa y muestran «No respaldado»; el inspector no agrega una afirmación nueva.
