# FDE-Bench v2

[English](../../README.md) · [中文](../zh/README.md) · [한국어](../ko/README.md) · [日本語](../ja/README.md) · **Español**

Un benchmark para agentes de ingeniería desplegada en el cliente (forward-deployed engineering) que cubre
**idiomas del cliente** (zh/en/ko/ja/es), **políticas de empresa** y una **dificultad realista**. Los modelos
abiertos y cerrados se comparan mediante un único protocolo compatible con OpenAI, y los arneses (harnesses) de
los proveedores (Claude Code, Codex, Gemini CLI, OpenCode), mediante un canal de cliente compartido basado en
MCP. Es autocontenido: no depende del código ni de los datos de ningún otro benchmark.

Diseño, puntuación y estado: [DESIGN.md](../../DESIGN.md). Orientación, trabajos relacionados y crítica:
[docs/DIRECTION.md](../DIRECTION.md).

**Explorar los casos:** https://sangbumchoi.github.io/FDE-Bench-v2/ — una página por caso (solicitud,
configuraciones, reglas, requisitos ocultos, preguntas clave, datos y respuestas guardados, hallazgos de la
revisión), que `fdebench2 build-site` reconstruye a partir de `cases/*/*/docs/<lang>/explainer.html` y que se
publica en la rama `gh-pages` con cada push (`.github/workflows/pages.yml`).

## Agradecimientos

Agradecemos a los autores de los trabajos de los que aprendió este benchmark:

- **FDE-Gym** (Yang et al., *FDE-Gym: The Last Mile of AI Delivery*, arXiv 2610.22350;
  [fde-gym.com](https://fde-gym.com/paper/), [casos](https://huggingface.co/datasets/DeepLethe/FDE-Gym),
  [arnés](https://github.com/deeplethe/fde-gym)). Sus cuatro niveles de encargo, las partes interesadas con guion y
  coste de contacto, la reproducción sobre tráfico de producción reservado y los criterios de admisión (no hacer
  nada vale 0, la referencia 1, la lectura literal del encargo y los atajos puntúan bajo) sirvieron de base para la
  auditoría de la respuesta correcta de este repositorio.
- **Baidu FDE-Bench** (arXiv 2610.14539), que introdujo el marco del ingeniero desplegado en el cliente (FDE) y el
  vocabulario de métricas (calidad frente a la referencia, DSR, Ask-F1, pass^k) que v2 conserva.
- **τ^τ-Bench** (arXiv 2609.04611) y **τ-bench** (arXiv 2406.12045), por el diseño de evaluar el agente construido
  con usuarios reservados y por el estimador pass^k.

v2 no comparte código ni datos con ellos: cada caso es original y se genera a partir de una semilla, y no se usaron
los casos de FDE-Gym, que tienen sus propias condiciones. Más trabajos relacionados en
[docs/DIRECTION.md](../DIRECTION.md), §2 y §9.

## Instalación

```bash
pip install -e '.[mcp,dev]'
cp configs/models.example.yaml configs/models.yaml   # set endpoints and API-key env vars
```

## Uso

```bash
fdebench2 cases                                   # <field>/<role>, role title, task type, locales
fdebench2 validate-case cases/*/*/                # contract checks for every case
fdebench2 export-dataset cases/<field>/<role>     # store a case's data and answers in dataset/
fdebench2 audit-case cases/<field>/<role>         # measure its ground truth, stored in dataset/audit.json
fdebench2 policies
# What an agent would get, without running one (Korean client, Japanese agent instructions, messy engagement):
fdebench2 prepare --case logistics/bakery_delivery_dispatcher --customer-locale ko --agent-locale ja \
    --policy startup_velocity --engagement messy
# A case with settings: hard tier, public rule seed 10 (same prompt and files as any other setting):
fdebench2 prepare --case healthcare/hospital_appointment_scheduler --difficulty hard --rule-seed 10
# The same tier with a private rule seed: a fresh draw of the same candidates, whose answer is stored nowhere:
fdebench2 prepare --case healthcare/hospital_appointment_scheduler --difficulty hard --rule-seed 4242
# One run with the reference harness and any OpenAI-compatible model from models.yaml:
fdebench2 run --case logistics/bakery_delivery_dispatcher --model qwen --customer-locale es
# Same with a vendor CLI:
fdebench2 run --case logistics/bakery_delivery_dispatcher --harness claude_code --model claude-opus-5-5
# Re-score an existing run under other policies (no agent re-run):
fdebench2 score runs/reference--qwen/<variant> --policy regulated_strict --policy startup_velocity
# Campaigns and reports:
fdebench2 campaign configs/experiments.example.yaml --dry-run
fdebench2 report runs/
```

`--difficulty` elige el nivel de contenido de un caso y `--rule-seed` sortea los parámetros de sus reglas, cada
uno entre sus candidatos (por defecto, la primera semilla de reglas pública del caso; cualquier otro entero es una
semilla privada, un sorteo cuya solución no se guarda en ningún sitio). Cada par de nivel y semilla de reglas es una
solución correcta de un mismo conjunto de datos, con la misma vista del agente en todas ellas. `--engagement`
(full_spec / standard / messy) cambia la modalidad con la que se entrega el trabajo. Véase
[cases/README.md](../../cases/README.md#difficulty-one-dataset-tiers-and-rule-seeds).

Ejes disponibles en todos los comandos: `--customer-locale {zh,en,ko,ja,es}`, `--agent-locale {zh,en,ko,ja,es}`,
`--policy NAME`, `--difficulty {easy,medium,hard}`, `--rule-seed N`, `--engagement {full_spec,standard,messy}`,
`--condition {full,interact,interact_req,hidden}`
(para forzar una condición en las ablaciones), `--seed N`.

## Estructura

```
cases/<field>/<role>/  case.yaml, case.py, locales/<lang>/{request.md, requirements.md, targets.yaml},
                       dataset/ (data per locale, hidden inputs, answer/answers.csv: one row per setting),
                       docs/<lang>/{README.md (tiers, rule parameters, numbers per setting), REVIEW.md,
                       explainer.html}, README.md (generated index of docs/ and answer/), GT.md (audited cases)
cases/README.md        catalog of cases by field   cases/fields.yaml  field names in 5 locales
cases/docs/<lang>/     index.html: the catalog's page in each language (the site's home page)
fdebench2/
  cases.py           Case interface and loader
  casekit.py         helpers for case authors        validate.py   case contract checks
  llm.py             OpenAI-compatible client, model registry, scripted model for tests
  transforms/        language · policy · engagement (noise, events) · variant composition (setting)
  prompts/           agent instructions per locale · messages.yaml (all generated messages, 5 locales)
  customer.py        simulated client               session.py    client channel, events, transcript
  agents/            reference tool-calling harness · vendor CLI adapters
  mcp_bridge.py      MCP server giving CLI agents the client channel
  program.py         runs Program deliverables on hidden inputs, isolated (program_host.py inside)
  scoring/           extraction · clarification judges · policy score · report
configs/             policies/ engagement.yaml models.example.yaml experiments.example.yaml
docker/              Dockerfile.agent: the image for isolated runs (tools and vendor CLIs only)
docs/                DIRECTION.md · specs/ (unbuilt cases) · <lang>/README.md (this README in zh, ko, ja, es)
tests/
```
