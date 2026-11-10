# Enviar resultados a la clasificación

Cualquiera puede poner un sistema (un modelo con un arnés) en la clasificación de FDE-Bench v2: se ejecuta una
campaña, se empaquetan sus resultados con `fdebench2 submit` y se abre una pull request que añade un solo archivo,
`leaderboard/<name>.json`. El sitio (`fdebench2 build-site`) muestra cada archivo de
[leaderboard/](../../leaderboard/) como una fila de la página de clasificación.

## 0. Pruebe primero un caso (sin modelo ni clave de API)

```bash
pip install -e .
fdebench2 try                                   # el caso por defecto, medium, la primera semilla de reglas pública
fdebench2 try --case logistics/bakery_delivery_dispatcher --difficulty hard --lang ko
fdebench2 try --submission my_deliverable/      # puntúa del mismo modo su propia carpeta con el entregable
```

`try` muestra lo que se le pide a la IA, los archivos que recibe, cuántos hechos solo conoce el cliente y la escala
de puntuación; después puntúa la solución literal del caso, la forma de trabajar del cliente y la solución de
referencia (y su carpeta) en esa configuración, con la política por defecto. La interacción se puntúa como en un
envío sin conexión: no se hizo ninguna pregunta, así que Ask-F1 es 0, y la política por defecto no le da peso. Sin
un modelo que convierta los archivos, su carpeta debe contener el entregable con los nombres que lee el evaluador
(`deliverables:` en el `case.yaml` del caso, o `program/` con el archivo de entrada en un caso de programa).

## 1. Ejecute una campaña

Un primer vistazo, para desarrollo (9 ejecuciones, sin docker, semillas de reglas públicas):

```bash
cp configs/models.example.yaml configs/models.yaml      # un endpoint y la variable de entorno con su clave de API
fdebench2 campaign configs/experiments.starter.yaml
fdebench2 report runs-starter/
```

Una entrada en la clasificación ejecuta la **ronda** vigente
([leaderboard/rounds.yaml](../../leaderboard/rounds.yaml)): todos los casos, en tres dificultades, con las tres
semillas de reglas de la ronda y tres intentos cada una, en docker. Son 351 ejecuciones, las mismas para todos los
sistemas. `configs/experiments.leaderboard.yaml` es esa campaña; indique en ella su agente y no cambie nada más:

```yaml
agents:
  - {harness: reference, model: my-model}     # un nombre de endpoint de configs/models.yaml, o el arnés de un proveedor
```

```bash
fdebench2 campaign configs/experiments.leaderboard.yaml --dry-run   # 351 ejecuciones
fdebench2 campaign configs/experiments.leaderboard.yaml
fdebench2 report runs-leaderboard/              # revise las tablas antes de empaquetarlas
```

## 2. Empaquete los resultados

```bash
fdebench2 submit runs-leaderboard/ --name "My system" --model my-model-2026-10 --harness reference \
    --version 1.2 --flag web_tools=off --flag max_steps=400 --flag budget_usd_per_run=5 \
    --date 2026-11-06 --out leaderboard/my-system.json
```

| Opción | Significado |
|---|---|
| `runs-leaderboard/` | el directorio de resultados de la campaña (`<agent>/<run key>/result.json`) |
| `--name` | el nombre del sistema en la clasificación |
| `--model`, `--harness` | lo que muestra la clasificación (por defecto, el modelo y el arnés de las propias ejecuciones) |
| `--version` | la versión de su sistema |
| `--flag KEY=VALUE` | un ajuste que se declara; se puede repetir (herramientas web, presupuestos de pasos y de tokens, herramientas adicionales, prompts) |
| `--date` | la fecha del envío, `YYYY-MM-DD` (por defecto, hoy en UTC) |
| `--agent` | la etiqueta del agente, `<harness>--<model>`, cuando el directorio contiene ejecuciones de varios agentes |
| `--cases` | la carpeta de los casos (por defecto, `cases/`), con la que se distinguen las semillas de reglas públicas de las privadas y se calcula el hash de los casos |
| `--rounds` | el archivo de las rondas (por defecto, `leaderboard/rounds.yaml`) |

Muestra el archivo que ha escrito y un resumen de una línea: las ejecuciones puntuadas, los casos, la puntuación
final media con su intervalo y el estado (`ranked` con su ronda, o `development` con los motivos).

## 3. Envíelo

Abra una pull request que añada `leaderboard/<name>.json` (un archivo por sistema; una versión nueva de un sistema
sustituye a su archivo). Explique en la descripción cómo se hicieron las ejecuciones: el arnés y su versión, los
presupuestos, si las herramientas web estaban activadas y todo lo demás que un lector necesite para reproducirlas.

## Reglas

- **Ejecute la ronda.** Un envío solo se clasifica cuando ejecutó completa una ronda de
  [leaderboard/rounds.yaml](../../leaderboard/rounds.yaml): todos los casos, en cada uno de los niveles y con cada
  una de las semillas de reglas de la ronda, en las condiciones de la ronda (cliente y agente en inglés, la política
  `baseline`, la modalidad `standard`). Todos los sistemas de una ronda responden a las mismas configuraciones, así
  que los resultados son comparables y nadie elige sus propias semillas. Las semillas de reglas de la ronda no están
  entre las semillas de reglas públicas de ningún caso: sus respuestas no se guardan en ningún sitio del
  repositorio. Cada ronda nueva recibe semillas nuevas, y la clasificación muestra cada ronda por separado.
- **Todo lo demás es `development`.** Las ejecuciones con semillas de reglas públicas, con semillas propias, con
  solo una parte de los casos o de los niveles, o en otro idioma o con otra política son bienvenidas, y se muestran
  sin clasificar, con el motivo.
- **Intentos ≥ 3.** Cada configuración debe ejecutarse al menos 3 veces (`trials: 3`); con menos, el envío es
  `development`.
- **Herramientas web desactivadas, o registradas.** Una ejecución no debe buscar el caso en internet. Si el arnés
  tiene herramientas web, desactívelas (`--flag web_tools=off`) o conserve sus registros e indíquelo
  (`--flag web_tools=logged`).
- **Declare el arnés y los presupuestos.** Indique como flags el arnés y su versión y cada presupuesto (pasos,
  tokens, dólares, tiempo de reloj).
- **El benchmark tal como se publicó.** Ejecute una copia del repositorio sin modificar. El envío registra el commit
  y un hash de los archivos de cada caso, así que los resultados obtenidos con otras versiones de los casos no se
  comparan.
- **Sin ediciones a mano.** El JSON es el que escribió `fdebench2 submit`.
- **Los resultados los declara cada participante.** El evaluador y las soluciones de referencia son código de este
  repositorio, así que cualquiera que lo ejecute puede calcular las respuestas de una ronda. El agente no debe
  hacerlo: en el sandbox solo ve su espacio de trabajo (`isolation: strict`). La clasificación se apoya en eso, como
  todas las clasificaciones cuyos resultados declaran los propios participantes; un envío que no se pueda reproducir
  a partir de su descripción puede retirarse.

## El formato

Un objeto JSON, `"format": "fdebench2-submission/1"`:

| Campo | Contenido |
|---|---|
| `kind` | `"system"` (un envío) o `"anchors"` (los puntos de anclaje de los propios casos, véase más abajo) |
| `example` | `true` solo en el archivo de ejemplo |
| `system` | `name`, `model`, `harness`, `version`, `agent_label` (el `<harness>--<model>` de las ejecuciones), `max_steps`, `flags` (`{key: value}`), `date` |
| `benchmark` | `framework_version`, `git_commit`, `git_dirty` (cambios sin confirmar en `cases/`, `fdebench2/` o `configs/`), `cases`: `{case id: hash of its files}` (para cada id de caso, el hash de sus archivos; es el hash que usa la huella de una ejecución: los archivos del caso salvo sus documentos y su auditoría guardada) |
| `seeds` | `kind`: `private`, `public`, `mixed` o `none`, y las semillas de reglas `public` y `private` usadas |
| `trials` | el menor número de intentos que tuvo alguna variante |
| `status` | `ranked` (una ronda completa, `trials` ≥ 3) o `development`; `anchor` para los puntos de anclaje |
| `round` | el id de la ronda que ejecutó un envío clasificado; si no, null |
| `status_reasons` | por qué un envío no está clasificado |
| `aggregate` | las medias de abajo, cada una `{mean, ci: [low, high], n_cases}`, más `n_runs`, `n_scored`, `n_cases` y `statuses` (ejecuciones por estado) |
| `runs` | un registro por ejecución (abajo) |

**Agregado.** Medias macro por caso, como las calcula `fdebench2 report`: dentro de un caso, todas las semillas de
reglas pesan lo mismo (la media de las ejecuciones de una semilla y, después, la de las semillas), y después todos
los casos pesan lo mismo. `ci` es el intervalo bootstrap del 95 % sobre los casos (2000 remuestreos, semilla fija).
Las ejecuciones que terminaron con un error del arnés o de la infraestructura (`harness_error`, `infra_error`) se
cuentan en `statuses` y quedan fuera de todas las medias.

| Métrica | Significado |
|---|---|
| `final` | la puntuación compuesta con la política de la ejecución (0 cuando falla una condición obligatoria) |
| `validity` | proporción de ejecuciones cuyo entregable no incumplió ninguna regla |
| `quality` | calidad normalizada: la forma de trabajar del cliente del caso vale 0 y su solución de referencia vale 1 (0 si el entregable es inválido) |
| `ask_f1` | Ask-F1 sobre los hechos del cliente (ejecuciones en las que se podía preguntar al cliente) |
| `enforced_share` | proporción de los hechos del cliente que el entregable aplica, sobre los hechos que midió la comprobación directa del caso |
| `cost_usd`, `total_tokens` | por ejecución: el agente que resuelve, el cliente, el extractor y los jueces (los tokens propios de un agente de línea de comandos aún no se leen) |

**Ejecuciones.** Cada registro: `case`, `tier`, `rule_seed`, `seeds` (`public`, `private`, `unknown` para un caso
que no está en esta versión, o null), `trial`, `noise_seed`, `customer_locale`, `agent_locale`, `policy`,
`engagement`, `condition`, `world_seed`, `status`, `final`, `valid`, `quality`, `ask_f1`, `targets` (el embudo de
los hechos que la IA debe preguntar: `n` hechos y, para `revealed`, `learned` y `enforced`, es decir, dicho por el
cliente, aprendido al preguntar y aplicado en el entregable, cuántos pasaron y cuántos se midieron,
`<stage>_measured`), `enforced_share`, `cost_usd`, `total_tokens` y la huella de la propia ejecución,
`fingerprint`.

**Puntos de anclaje.** Un archivo con `kind: "anchors"` contiene la solución literal, la forma de trabajar del
cliente y la solución de referencia de los casos, puntuadas sin conexión como las puntúa `fdebench2 try`, con
`anchors: {literal | baseline | reference: aggregate}` en lugar de `aggregate` y un campo `anchor` en cada
ejecución. La clasificación las muestra como filas de referencia, nunca clasificadas.
[leaderboard/anchors-2026-11.json](../../leaderboard/anchors-2026-11.json) las contiene para la ronda vigente; lo
escribe `fdebench2 anchors --round 2026-11 --out leaderboard/anchors-2026-11.json` con los niveles y las semillas de
reglas de la ronda, de modo que las filas de referencia y los sistemas clasificados responden a las mismas
configuraciones. Sin `--round`, el comando puntúa las semillas de reglas públicas y marca el archivo como ejemplo.
