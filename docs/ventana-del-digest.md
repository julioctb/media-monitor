# La ventana del digest: fechas, rescate vespertino y cortes múltiples

Referencia para leer las fechas de cualquier resumen (la escena completa está
en `backend/app/summaries/builder.py` → `resolve_digest_window` y
`es_short_label` en `digest.py`). Nada de esto se improvisa: todo es
determinístico y queda persistido en la fila del día.

## 1. La ventana nunca es «el día calendario» nomás

Cada digest cubre `window = [from, to)` en la zona del cliente:

- **Base**: `00:00 → 24:00` del día.
- **Rescate vespertino**: si la PRIMERA generación del día ocurre antes de las
  `12:00`, la ventana extiende **3 horas hacia la noche anterior**
  (`21:00 → 24:00` del día previo). Razón: las notas publicadas esa noche ya
  no alcances ningún corte del día previo y quedarían huérfanas entre dos
  resúmenes.

La ventana elegida se **persiste en `content.window_start`**: todos los
cortes siguientes del mismo día reconstruyen con exactamente la misma
ventana. Una nota no puede aparecer y desaparecer entre cortes del mismo día.

## 2. Por qué una nota figura «22 oct.» en el digest del 23

`when_label` (la fecha que ves ante cada nota) es la **fecha real de
publicación** de la mención más reciente del evento, en zona del cliente —
nunca el día del digest. Con el rescate activo, la ventana del 23 empieza
`22 oct 21:00`, y esas notas de la noche del 22 se etiquetan «22 oct.».

La franja `22 21:00–24:00` puede aparecer **en ambos digests** (el del 22 y
el del 23): es el solape diseñado del rescate. La etiqueta es la que
desambigua.

## 3. Varios cortes al día

`digest_hours` (CSV en Configuración) programa N cortes; cada uno
**regenera** el digest del día con la misma ventana persistida. El modo
(`llm`/`heuristic`), la narrativa y las notas se re-construyen; el histórico
queda en la fila única del día (sin filas por corte).

## 4. ¿Un corte a las 00:00?

Sí dispara el mismo efecto, y algo más:

- `00:00 < 12:00` → **el rescate vespertino se activa**: la ventana del día
  nuevo incluye `21:00–24:00` del día anterior.
- El día nuevo a las 00:00 apenas tiene minutos propios: el digest de ese
  corte es **casi solo la cola rescatada** del día anterior.
- **Solape**: la banda `21:00–24:00` ya estaba (parcial o totalmente) en el
  último corte del día anterior — lo publicado después de ese corte es
  contenido nuevo; lo anterior, duplicado etiquetado con su fecha real.
- Los cortes posteriores (08:00, 21:00…) regeneran con la misma ventana
  extendida, así que el digest final del día conserva el rescate aunque el
  corte de medianoche fuera el único matinal.

En corto: no rompe nada, pero un corte a las 00:00 produce un digest
casi vacío que duplica la cola nocturna ya cubierta. Si la intención es un
«cierre» del día que termina, el corte útil es el último de la noche
(21:00–23:00) del propio día — el sistema siempre construye el digest del
día en curso, nunca el del día anterior.
