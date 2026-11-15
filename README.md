# PATCH · MVP funcional

Simulador de evaluación y documentación de episodios de salud durante una misión a Marte. Usa pacientes ficticios, una interfaz Streamlit en español, persistencia SQLite y un enlace unidireccional con demora virtual.

**Demostración de software, no producto médico validado.** No contiene tratamientos ni diagnósticos automáticos. El entrevistador es un **mock determinista**: no se conecta a MedGemma, no interpreta respuestas ni reconoce emergencias en texto libre.

## Inicio rápido en Windows (PowerShell)

Requisito: **Python 3.11 o superior**. Descomprime el ZIP, abre PowerShell dentro de `patch-dev` y ejecuta:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Abre http://localhost:8501. No es necesario activar el entorno virtual. Como alternativa, `./start.ps1` prepara el entorno y arranca la aplicación; si PowerShell impide ejecutar scripts, usa los tres comandos anteriores sin cambiar políticas del sistema.

## Inicio en WSL / Linux / macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

También puedes ejecutar `bash start.sh`. En Ubuntu, si falta el módulo `venv`, instala el paquete `python3-venv` correspondiente a tu Python. La instalación inicial necesita acceso a PyPI; después la simulación no requiere red ni claves de API.

Detén el servidor con **Ctrl+C**. Para usar otro puerto agrega `--server.port 8502`.

## Cómo usarlo

1. En la barra lateral, elige N02, N04 o N06, revisa el motivo inicial y pulsa **Iniciar episodio nuevo**. Esto guarda la caja negra y crea `INITIAL_ALERT` inmediatamente, sin esperar al chequeo ni a la entrevista.
2. En **A bordo**, registra conciencia y respiración. No hay respuestas preseleccionadas: `YES/YES` habilita el mock; `UNKNOWN` bloquea la entrevista; `NO` registra compromiso actual y activa la ruta crítica ilustrativa. Usa únicamente decisiones ficticias del operador para la demo.
3. Responde las preguntas del mock. Consulta el guion privado del actor en **Simulador**; comunica únicamente lo que se haya preguntado. Las preguntas son genéricas, no una anamnesis adaptativa real.
4. Solicita una exploración. Después registra el resultado sintético disponible o ingresa valor, fuente, calidad y hora. Los datos referidos no se convierten automáticamente en mediciones. Puedes registrar `unknown`, `unavailable`, `denied` o una corrección que referencia el dato anterior.
5. Pulsa **Generar y enviar informe**. Se captura una plantilla SBAR con transcripción literal y datos registrados. El informe no finaliza la evaluación ni garantiza suficiencia clínica.
6. Avanza el reloj desde **Simulador**. El reloj no avanza por tiempo real. **Tierra** muestra exclusivamente paquetes recibidos, con contenido congelado, hora de creación, envío y recepción.
7. Exporta la traza JSON desde **Simulador**, o cada paquete recibido desde **Tierra**. El cierre del episodio requiere una nota y genera una actualización final.

Los recorridos completos están en [docs/SCENARIOS.md](docs/SCENARIOS.md).

## Implementado y simulado

| Componente | Estado |
|---|---|
| N02, N04, N06 | Configurados con datos y procedencia de la especificación adjunta |
| HSM | Implementación Python con `ASSESSMENT` y `CRITICAL`; recheck es una acción |
| Chequeo inicial | Entrada manual obligatoria, sin inventar respuestas de los guiones |
| Telemetría | FC/SpO₂ sintéticas minuto a minuto; 122 registros en T−60..T0, extremos incluidos |
| Persistencia | SQLite, transacciones, eventos y payloads inmutables, comandos con ID idempotente |
| Transporte | `QUEUED` → `IN_TRANSIT` → `DELIVERED`; cortes y recuperación; sin ACK ni retorno |
| Entrevistador / MedGemma | **Mock**, sin conexión LLM ni extracción automática de hallazgos |
| SBAR | Plantilla determinista con fuentes, horas, observaciones y transcripción |
| A/B/C | Campos ilustrativos para registrar valoración, pendientes de revisión clínica |
| Tests | No se agregaron ni se ejecutaron suites de tests, conforme a lo solicitado |

La aplicación puede generar informes aunque falten datos; los pendientes quedan explícitos. Los resultados de exámenes que no están definidos en el material se ingresan manualmente o se marcan no disponibles. No se inventó el resto de guiones mencionados por los adjuntos pero no suministrados.

## Datos y reinicio

La base se crea automáticamente en `data/patch_mvp.sqlite3`, relativa a esta carpeta. Cerrar/reabrir la aplicación conserva perfiles, episodios, reloj, observaciones, diálogo y cola. La selección del último episodio también se persiste. Para reiniciar una demostración, crea **un episodio nuevo**; el anterior permanece consultable.

El ZIP no incluye bases generadas, entornos virtuales, credenciales ni cachés. Para una base alternativa:

```powershell
$env:PATCH_DB_PATH = "C:\patch-data\mission.sqlite3"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

En WSL: `PATCH_DB_PATH=/ruta/mission.sqlite3 .venv/bin/python -m streamlit run app.py`.

Esta entrega adapta el scaffold a la especificación MVP de 14-11-2026. El esquema anterior y sus contratos incompletos no eran ejecutables; se reemplazaron por los del MVP. No hay migración de bases de una implementación anterior y no se reutilizan automáticamente. La aplicación es local, sin autenticación: no está preparada para exposición pública ni para datos reales de pacientes.

## Módulos

| Archivo | Responsabilidad |
|---|---|
| `app.py` | Vistas A bordo / Tierra / Simulador y formularios |
| `controller.py` | Comandos transaccionales, contexto permitido, informes y cronología |
| `contracts.py` | Modelos Pydantic y validaciones |
| `core_hsm.py` | Decisiones deterministas de estado y autorización de entrevista |
| `config_scenarios.py` | Configuraciones y datos privados de los guiones |
| `space_link_db.py` | SQLite, evidencia persistente y transporte diferido |
| `llm_anamnesis.py` | Interfaz del entrevistador y mock explícito |

Para integrar MedGemma más adelante, sustituye `InterviewBackend.generate(context)` respetando su retorno. El contexto ya excluye guiones, futuros eventos y resultados no registrados. El controlador verifica episodio, versión del estado y permisos antes de aceptar el turno. El mock actual es síncrono; una integración de red deberá implementar ejecución fuera de la transacción, timeout y tratamiento de fallos. No se afirma cancelación real de una inferencia en curso.

## Flujo Git

Conserva el flujo **rama de trabajo → dev → main**. En tu repositorio existente, crea una rama desde `dev`, copia los archivos de esta entrega, revisa los cambios y abre un PR hacia `dev`. Después integra la versión estable en `main` mediante otro PR. El ZIP no contiene `.git` ni publica cambios por sí solo.

```bash
git switch dev
git pull --ff-only origin dev
git switch -c feat/patch-mvp
# Copiar aquí los archivos de esta entrega y revisar git diff.
git add app.py contracts.py controller.py core_hsm.py config_scenarios.py space_link_db.py llm_anamnesis.py requirements.txt README.md docs .streamlit start.ps1 start.sh .gitignore
git commit -m "Implement PATCH MVP with scenarios and mock interview"
git push -u origin feat/patch-mvp
```

Consulta [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/RESULTS.md](docs/RESULTS.md) y [docs/CHANGELOG.md](docs/CHANGELOG.md).
