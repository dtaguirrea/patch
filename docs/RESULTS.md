# Estado de ejecución y alcance de revisión

Fecha de entrega: 14-11-2026, zona America/Santiago.

No se crearon ni ejecutaron suites de tests. Se revisó la sintaxis de los módulos, se arrancó Streamlit y se recorrieron manualmente comandos de la aplicación con datos ficticios en una base temporal excluida de la entrega.

| Recorrido manual | Resultado observado |
|---|---|
| Arranque Streamlit | Endpoint de salud HTTP 200, `ok` |
| N02 | Snapshot inicial de 122 muestras; chequeo explícito, conversación mock y PA 108/70; alerta e informe enviados en T0 recibidos en T+15 min |
| N04 | Evento T+2 cambia a CRITICAL y bloquea entrevista; INITIAL_ALERT recibido en T+22 min y CRITICAL_UPDATE en T+24 min |
| N06 | Informes creados en T+25 min y T+6 h 10 min, enviados ambos en T+7 h y recibidos en T+7 h 15 min |
| Fuente de temperatura N06 | 39,1 °C registrada como `crew_reported` |
| Persistencia | Los tres episodios permanecían al cerrar y reabrir SQLite |

En estos recorridos se seleccionó YES/YES como entrada ficticia del operador para demostrar la ruta de entrevista, no como dato aprobado del guion. No se incluyeron esas selecciones como valores por defecto del producto.

El navegador remoto no pudo acceder a la instancia local; **no se verificó visualmente el diseño ni se afirma una revisión interactiva completa de todos los controles**. El servidor arrancó y se ejecutó el código de renderizado sin sesión de navegador. La revisión descrita no equivale a validación clínica, pruebas exhaustivas, rendimiento de MedGemma ni certificación de seguridad.
