# PATCH

**PATCH (Protocol-Assisted Triage, Communication & Handoff)** será un simulador
de episodios de salud durante una misión a Marte. Usará datos ficticios y
modelará la comunicación demorada entre la Nave y Tierra. El proyecto está en
etapa de estructura inicial; la implementación se realizará posteriormente con
Python 3.11, Streamlit, SQLite, Pydantic y pytest.

## Módulos

- `app.py`: interfaz de usuario y punto de entrada de la aplicación Streamlit.
- `contracts.py`: contratos, modelos de datos y validaciones compartidas.
- `config_scenarios.py`: configuración de los escenarios y sus datos ficticios.
- `core_hsm.py`: máquina de estados y lógica de progresión de los episodios.
- `space_link_db.py`: persistencia SQLite y cola de mensajes entre Nave y Tierra.
- `llm_anamnesis.py`: futura integración para apoyar la entrevista de anamnesis.

## Escenarios previstos

- **A — Entrevista durante el retraso de comunicaciones:** la Nave realiza una
  entrevista mientras los mensajes esperan el enlace demorado.
- **B — Deterioro simulado y aviso diferido a Tierra:** la condición simulada
  empeora y la notificación llega a Tierra después del retraso.

Ambos escenarios son trabajo futuro y todavía no están implementados.

## Cómo trabajamos en Git

El flujo de trabajo es **rama de trabajo → `dev` → `main`**:

1. `dev` es la rama de integración. Cada tarea comienza desde `dev` actualizado
   en una rama propia, como `feat/hsm`, `fix/cola-mensajes` o
   `docs/escenarios`.
2. Al terminar una tarea, publica su rama y abre un pull request con base
   `dev` y compare la rama de trabajo. El PR debe indicar qué cambió y cómo se
   revisó.
3. Cuando `dev` esté listo para una entrega, abre un pull request con base
   `main` y compare `dev`. `main` contiene las versiones estables. Las
   integraciones a `dev` y `main` se hacen por PR.

Comandos habituales:

```bash
git switch dev
git pull --ff-only origin dev
git switch -c feat/mi-tarea
# ... realizar y revisar cambios ...
git push -u origin feat/mi-tarea
```

Para esta entrega, el primer pull request debe usar `dev` como **base** y la
rama de trabajo publicada como **compare**.
