# Cómo contribuir a FDE-Bench v2

[English](../../CONTRIBUTING.md) · [中文](../zh/CONTRIBUTING.md) · [한국어](../ko/CONTRIBUTING.md) · [日本語](../ja/CONTRIBUTING.md) · **Español**

Gracias por ayudar. Esta página explica qué se puede aportar, cómo se construye un caso nuevo, qué nivel tiene que
alcanzar y qué necesita una pull request (PR). Contexto: el [README](README.md), el formato de los casos en
[DESIGN.md](../../DESIGN.md), §3, el catálogo en [cases/README.md](../../cases/README.md) y las reglas de diseño de los
casos nuevos en [docs/DIRECTION.md](../DIRECTION.md), §5.

## Qué se puede aportar

| Aportación | Qué es | Por dónde empezar |
|---|---|---|
| **Un caso nuevo** | Un rol del catálogo ([cases/README.md](../../cases/README.md), especificaciones en [docs/specs/](../specs/README.md)) construido según el contrato de los casos | Un issue con la plantilla *Case proposal* y luego el proceso de abajo |
| **Una traducción o una revisión nativa** | Corregir o revisar los textos de un idioma: `locales/<lang>/` (request, requirements, targets, summary, explainer.yaml), `docs/<lang>/README.md` y `REVIEW.md`, `fdebench2/prompts/*.yaml`, `docs/<lang>/` | Una PR para el idioma que se lee de forma nativa, indicando qué archivos se revisaron |
| **Una revisión de las respuestas del cliente** | Un veredicto en el `CLIENT_REVIEW.md` de un caso auditado: ¿el pasaje del que responde el cliente de cada idioma contesta a la pregunta natural, correctamente y sin dar de más? | La sección de abajo |
| **Un informe de error** | Puntuación incorrecta, un hueco del validador, un fallo, una página rota, un cliente que filtra o inventa una regla | Un issue con la plantilla *Bug report* |
| **El envío de resultados** | Ejecuciones de un modelo o un arnés sobre el benchmark | [docs/SUBMITTING.md](../SUBMITTING.md) |

### Revisión de las respuestas del cliente

Cada caso auditado (`audited: true` en case.yaml) tiene un `CLIENT_REVIEW.md` junto a su case.yaml. Para cada hecho da
la pregunta que haría un ingeniero, la línea de `requirements.md` de la que responde el cliente de cada idioma y una
comprobación previa automática. Todas las líneas `Reviewer verdict:` siguen vacías.

- Lea los pasajes en los idiomas que lee de forma nativa.
- En la línea `Reviewer verdict:` escriba `OK` o `Problem`, los idiomas que comprobó y, si hay un problema, cuál es:
  un número erróneo o ausente, una respuesta ambigua o un pasaje que responde más de lo preguntado.
- `CLIENT_REVIEW.md` es un archivo generado (`make_client_review.py` lo reescribe). Envíe los veredictos en una PR
  propia y no regenere el archivo en ella. Una corrección de los requisitos va en otra PR.

## El proceso de un caso

```bash
fdebench2 new-case <field>/<role>             # add --program when the deliverable is code run on hidden inputs
# write case.yaml and case.py, then every text in all five locales (zh, en, ko, ja, es)
fdebench2 export-dataset cases/<field>/<role> # store data and answers in dataset/; also writes the explainer pages
fdebench2 validate-case cases/<field>/<role>  # the case contract, on the public world and world seeds 1-3
fdebench2 audit-case cases/<field>/<role>     # the ground truth audit, stored in dataset/audit.json
python -m pytest -q                           # the repository's tests
```

1. **Proponer.** Abra un issue con la plantilla *Case proposal*: el rol, el cliente, el entregable, los hechos ocultos
   y cómo cambia cada uno la respuesta. Elija un rol del catálogo o diga a qué campo pertenece (`cases/fields.yaml`).
2. **Crear el esqueleto.** `fdebench2 new-case` escribe case.yaml, case.py, los cinco idiomas y el README en cada
   idioma, con todas las partes obligatorias marcadas TODO. Tome como modelo los casos construidos que nombra su
   docstring (`fdebench2/scaffold.py`).
3. **Escribir el mundo y el evaluador** en case.py: `build_world`, `write_data`, `reference_solution`,
   `baseline_solution`, `literal_solution`, `score`, `violating_examples`; para una auditoría también `ablations`,
   `shortcuts`, `robust_solution`, `best_known_solution` u `objective_bound` ([DESIGN.md](../../DESIGN.md), §3).
4. **Escribir los textos en los cinco idiomas:** `locales/<lang>/request.md`, `requirements.md`, `targets.yaml`,
   `summary.yaml`, `explainer.yaml` (salvo en) y `docs/<lang>/README.md`. Cada idioma se redacta de forma nativa, no
   como una traducción palabra por palabra, con los mismos ids de objetivos, marcadores `{{param}}` y marcas de
   configuración en todos.
5. **Exportar** con `fdebench2 export-dataset` y **validar** con `fdebench2 validate-case` hasta que no informe de
   ningún problema. Corrija los avisos o explíquelos en el `docs/en/REVIEW.md` del caso.
6. **Auditar** con `fdebench2 audit-case` (de 10 a 40 minutos). Cuando el caso la supere, ponga `audited: true` y
   vuelva a ejecutar `validate-case`: un caso auditado falla si su auditoría falta o está desfasada.
7. **Añadir el caso al catálogo** ([cases/README.md](../../cases/README.md)), regenerar las páginas de inicio
   (`fdebench2 explain-case cases/<field>/<role>`), pasar las pruebas y abrir una PR.

## El nivel que debe alcanzar un caso

- `fdebench2 validate-case` no informa de ningún problema, en el mundo público y en las semillas de mundo 1-3.
- La escala de calidad mide al menos un 5 % en cada configuración pública: |referencia − línea base| / |referencia| ≥ 0,05.
- La solución literal (la solicitud hecha tal como está escrita, solo con lo que ve el agente) es inválida o puntúa
  como mucho 0,2 en cada configuración pública.
- Lo que ve el agente (solicitud y archivos) es idéntico byte a byte en todas las configuraciones; solo cambian los
  hechos del cliente.
- Cada regla tiene una clase, y exactamente una regla de negocio es la costumbre que se puede flexibilizar.
- En un caso auditado: cada hecho del cliente pesa (malinterpretar solo ese hecho invalida el entregable o cuesta al
  menos 0,10 de calidad en cada nivel en que está en vigor), cada atajo está cerrado (inválido o como mucho 0,5) y
  preguntar vale al menos 0,10 por nivel.
- Sin datos personales reales: cada persona, empresa, dirección y número es generado.
- Solo contenido original: nada copiado de otro benchmark, conjunto de datos o documento cuyas condiciones no lo
  permitan. FDE-Bench v2 no comparte código ni datos con otros benchmarks.

## Lista de comprobación de la PR

- [ ] Un tema por PR (un caso, una traducción, un grupo de veredictos, una corrección).
- [ ] `fdebench2 validate-case` pasa en todos los casos tocados.
- [ ] Se volvió a ejecutar `fdebench2 export-dataset` tras cualquier cambio en el código o los textos de un caso, y
  `dataset/` está incluido en el commit.
- [ ] Casos auditados: se volvió a ejecutar `fdebench2 audit-case` si cambiaron las fuentes, y `dataset/audit.json`
  está al día.
- [ ] Caso nuevo: escala de calidad ≥ 5 %, solución literal ≤ 0,2 y la vista del agente idéntica en todas las
  configuraciones.
- [ ] Los cinco idiomas se actualizaron a la vez; la redacción nativa se revisó donde fue posible.
- [ ] Sin datos personales reales; solo contenido original.
- [ ] El catálogo y las páginas de inicio se regeneraron (`fdebench2 explain-case`) al añadir o renombrar un caso.
- [ ] `python -m pytest -q` pasa.
- [ ] Mensajes de commit sencillos: qué cambió y por qué.
