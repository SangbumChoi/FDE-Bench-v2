# FDE-Bench v2

[English](README.md) · [中文](README.zh.md) · [한국어](README.ko.md) · [日本語](README.ja.md) · **Español**

Un benchmark para agentes de ingeniería desplegada en el cliente (forward-deployed engineering) que cubre
**idiomas del cliente** (zh/en/ko/ja/es), **políticas de empresa** y una **dificultad realista**. Los modelos
abiertos y cerrados se comparan mediante un único protocolo compatible con OpenAI, y los arneses (harnesses) de
los proveedores (Claude Code, Codex, Gemini CLI, OpenCode), mediante un canal de cliente compartido basado en
MCP. Es autocontenido: no depende del código ni de los datos de ningún otro benchmark.

Diseño, puntuación y estado: [DESIGN.md](DESIGN.md). Orientación, trabajos relacionados y crítica:
[docs/DIRECTION.md](docs/DIRECTION.md).

**Explorar los casos:** https://sangbumchoi.github.io/FDE-Bench-v2/ — una página por caso (solicitud,
configuraciones, reglas, requisitos ocultos, preguntas clave, datos y respuestas guardados, hallazgos de la
revisión), que `fdebench2 build-site` reconstruye a partir de `cases/*/*/explainer.html` y que se publica en la
rama `gh-pages` con cada push (`.github/workflows/pages.yml`).

## Instalación

```bash
pip install -e '.[mcp,dev]'
cp configs/models.example.yaml configs/models.yaml   # set endpoints and API-key env vars
```

## Uso

```bash
fdebench2 cases                                   # <field>/<role>, role title, task type, locales
fdebench2 validate-case cases/*/*/                # contract checks for every case
fdebench2 export-dataset cases/<field>/<role>     # store a case's data and ground truth in dataset/
fdebench2 policies
# What an agent would get, without running one (Korean client, Japanese agent instructions, messy engagement):
fdebench2 prepare --case logistics/bakery_delivery_dispatcher --customer-locale ko --agent-locale ja \
    --policy startup_velocity --engagement messy
# A case with settings: hard tier under rule set B (same prompt and files as any other setting):
fdebench2 prepare --case healthcare/hospital_appointment_scheduler --difficulty hard --ruleset B
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

`--difficulty` elige el nivel de contenido de un caso y `--ruleset` (A/B/C), los parámetros de sus reglas: nueve
soluciones correctas de un mismo conjunto de datos, con la misma vista del agente en todas ellas. `--engagement`
(full_spec / standard / messy) cambia la modalidad con la que se entrega el trabajo. Véase
[cases/README.md](cases/README.md#difficulty-one-dataset-nine-ground-truths).

Ejes disponibles en todos los comandos: `--customer-locale {zh,en,ko,ja,es}`, `--agent-locale {zh,en,ko,ja,es}`,
`--policy NAME`, `--difficulty {easy,medium,hard}`, `--ruleset {A,B,C}`, `--engagement {full_spec,standard,messy}`,
`--condition {full,interact,interact_req,hidden}`
(para forzar una condición en las ablaciones), `--seed N`.

## Estructura

```
cases/<field>/<role>/  case.yaml, case.py, locales/<lang>/{request.md, requirements.md, targets.yaml},
                       dataset/ (data per locale, hidden inputs, ground truth per setting),
                       README.md for cases with settings (tiers x rule sets)
cases/README.md        catalog of cases by field   cases/fields.yaml  field names in 5 locales
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
tests/
```
