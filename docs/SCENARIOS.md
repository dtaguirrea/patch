# Recorridos de demostración

Todos los personajes y valores son ficticios. Usa una base local sin datos de personas reales. Las respuestas a conciencia/respiración deben ser decisiones explícitas del operador: los adjuntos no suministran una respuesta aprobada por caso. Elegir YES/YES para un recorrido favorable es una decisión de demostración, no un dato clínico extraído del guion.

## N02 · Entrevista y hallazgo digestivo

1. Inicia N02 con demora de 15 minutos. La alerta inicial ya existe en la cola y Tierra está vacía.
2. Registra el chequeo manual y responde el mock. Cuando pregunte por digestión/deposiciones, comunica la información del guion privado: oscuras desde ayer, casi negras, pegajosas y de olor intenso, dos episodios. No atribuyas diagnóstico confirmado a ese relato.
3. Cuando pregunte por medicamentos, informa ibuprofeno un par de veces esa semana. Estos datos no estaban en el perfil inicial ni en `INITIAL_ALERT`.
4. Solicita PA y registra el valor sintético 108/70. Opcionalmente solicita otras exploraciones disponibles. No hay PA ortostática: se mantiene el conflicto de microgravedad como pendiente clínico.
5. Genera el informe y avanza a T+00:15. Si el informe fue creado en T0, ambos paquetes llegan en T+15 min; si fue posterior, llega 15 min después de su envío.
6. En Tierra compara la alerta inicial con el informe: los datos descubiertos posteriormente aparecen solo en la segunda instantánea.

## N04 · Interrupción independiente del mock

1. Inicia N04 con demora de 22 minutos. Registra el chequeo y comienza la entrevista si corresponde.
2. Desde Simulador pulsa **Activar deterioro N04 · avanzar a T+00:02**. El botón usa el mismo motor que cualquier avance de reloj y no duplica el evento si vuelve a ejecutarse.
3. El motor registra el relato de voz ronca/dificultad respiratoria y FC 124 / SpO₂ 92, cambia a `CRITICAL`, invalida la pregunta anterior y genera `CRITICAL_UPDATE`.
4. Regresa a A bordo: la entrevista está bloqueada y aparecen los campos ilustrativos A/B/C. La PA 90/58 todavía no es una observación.
5. Solicita PA y registra el resultado del guion: ahora sí queda 90/58 como `exam_entry`. Puedes registrar los campos descriptivos A/B/C manualmente; no se proporcionan tratamientos.
6. Si generas otro informe, tendrá esos nuevos datos. Avanza a T+00:22 para ver la alerta inicial y a T+00:24 para recibir la actualización del evento. Informes posteriores llegan 22 min después de su envío.

`CRITICAL` no vuelve automáticamente a `ASSESSMENT` por un chequeo posterior o por enviar un informe. Un episodio nuevo permite reiniciar la demo.

## N06 · Corte, reevaluación y recuperación de cola

1. Inicia N06, demora de 15 min (valor propuesto [D]). Completa el chequeo manual y la primera conversación.
2. Si comunicas la temperatura inicial, solicita Temperatura y registra **38,4**, fuente `crew_reported`, hora **Minutos antes = 10** en T0. No uses el botón de resultado sintético: el guion no aporta una medición nueva del termómetro.
3. Solicita PA si corresponde y registra 124/78. Avanza a T+00:25. El motor ya entregó la alerta inicial en T+00:15 y procesó el corte de T+00:20.
4. Desde A bordo genera el primer informe. Debe quedar `QUEUED`, sin hora de envío ni llegada.
5. Salta a **T+06:00** (seis horas). Se conserva el episodio y el diálogo; aparecen FC 112, SpO₂ 97 y temperatura 39,1 como declaración `crew_reported`. La entrevista vuelve a pedir el chequeo de conciencia/respiración.
6. Completa el nuevo chequeo manual, responde sobre evolución y registra nuevas exploraciones si corresponde. La PA de la primera fase sigue fechada a T0; solicitar y registrar otra PA produce 104/68 a la nueva hora.
7. Salta a **T+06:10** y genera el segundo informe desde A bordo. También queda `QUEUED`.
8. Salta a **T+07:00**: vuelve el enlace y ambos informes pasan a `IN_TRANSIT`, enviados en T+7 h, con llegada prevista T+7 h 15 min.
9. Salta a **T+07:15**: Tierra recibe ambos, conservando creación, observaciones y transcripciones de cada fase. Exporta la traza.

Los informes no se crean automáticamente al avanzar el reloj. Los horarios T+25 min y T+6 h 10 min son instantes sugeridos para pulsar el botón. Los cambios manuales de enlace no cancelan los eventos programados del escenario. Los paquetes ya enviados siguen viajando durante el corte.

## Revisión y cierre

**Pedir revisión humana** bloquea la entrevista, requiere nuevo chequeo y envía una actualización; no declara una emergencia universal ni una respuesta inmediata de Tierra. **Cerrar episodio** solicita una nota y envía el registro final. No da el alta ni declara recuperación.

El cierre detiene los nuevos eventos clínicos y muestras de ese episodio. El reloj puede seguir avanzando para entregar paquetes; si lo cerraste durante un corte, usa **Restablecer enlace** para liberar la cola, ya que el cronograma del episodio cerrado no continúa.
