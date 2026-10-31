"""Parámetros de chat compartidos para llamadas LLM mecánicas.

Único punto de verdad para ``chat_template_kwargs``: los modelos híbridos
tipo Qwen en vLLM traen el razonamiento encendido por defecto y, en tareas
mecánicas (clasificación, extracción, resumen, probe), eso consume el
``max_tokens`` antes de producir ``content`` (null) y multiplica la latencia
hasta romper los timeouts del worker. Aquí se declara una sola vez que esas
llamadas quieren respuesta directa.

Nota: esto NO apaga el razonamiento del servidor para otros clientes
(Hermes); es un selector por petición, que es justo lo que el endpoint
expone para este caso.
"""

NO_THINK_CHAT_KWARGS: dict = {"enable_thinking": False}
