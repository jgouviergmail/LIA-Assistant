# Dirigir una IA que programa

> Informe de experiencia — un sistema completo, del diseño a la producción.

**Versión**: 2.0
**Fecha**: 2026-08-23
**Aplicación**: LIA v1.42.4
**Licencia**: AGPL-3.0 (Open Source)

---

## 1. Lo esencial

LIA es un asistente de IA multiagente completo — conectores de negocio, voz, memoria, conexiones entre usuarios, seis idiomas — diseñado, desarrollado y operado en producción de forma continua, como proyecto personal.

La casi totalidad del código fue escrita por una IA, bajo dirección humana: un referencial de ingeniería escrito, controles automáticos bloqueantes, revisión sistemática, auditorías recurrentes. El resultado está medido: **8,3/10** en la auditoría técnica sobre 24 perímetros. El repositorio es open source; las conclusiones de la auditoría — fortalezas y debilidades — se asumen y se resumen en este documento.

| Indicador | Valor |
| --- | --- |
| Código escrito por una IA — dirigida, encuadrada, controlada | **≈ 100 %** |
| Líneas de código (sin tests) — 44 dominios funcionales | **580.000** |
| Tests automatizados, ejecutados en cada commit y entrega | **31.500+** |
| Decisiones de arquitectura documentadas (ADR) | **266** |
| Versiones entregadas a ritmo regular | **249** |
| Idiomas, paridad verificada automáticamente | **6** |
| Auditoría técnica sobre 24 perímetros | **8,3/10** |

Convicción de experiencia: el desarrollo asistido por IA es industrializable hoy. El factor limitante no es la herramienta — es el marco de dirección que se le da.

## 2. El enfoque

La IA generativa transforma a la vez lo que los equipos producen y la forma en que lo producen. Sobre ambos temas, no quería fundar mis convicciones en los discursos del mercado: elegí confrontarme con la realidad completa de un sistema de IA en producción — los costes, los riesgos, la explotación, la deuda — y con la realidad del desarrollo asistido por IA, practicándolos hasta el final.

El terreno de ejercicio: LIA, un asistente de IA conversacional multiagente — correo, agenda, contactos y archivos en Google, Apple y Microsoft, interfaz de voz en tiempo real, memoria a largo plazo, búsqueda documental, un personaje animado que lo encarna — autoalojado y multilingüe.

Las restricciones eran voluntarias: solo, fuera del tiempo profesional, presupuesto de hardware mínimo, y la IA como único desarrollador. Este proyecto no mide por tanto una velocidad individual; mide lo que una dirección exigente obtiene de una IA correctamente encuadrada.

*Base técnica: FastAPI · Next.js/React · LangGraph (orquestación de agentes) · PostgreSQL · Redis · Docker · Prometheus/Grafana/Loki/Tempo · 7 proveedores de modelos de IA integrados.*

## 3. El método

Una IA que programa produce volumen; solo produce calidad bajo restricción. Cuatro dispositivos sostuvieron este proyecto — ninguno es una herramienta, los cuatro son actos de gestión:

- **Un referencial escrito, como para un equipo.** Reglas de arquitectura, convenciones, patrones impuestos con su ejemplo canónico en el código, trampas conocidas documentadas — versionados en el repositorio, exigibles en cada entrega.
- **Controles automáticos bloqueantes.** Cada regla estructurante está respaldada por un control que rechaza el commit no conforme: tipado estricto, análisis de código, detección a medida de los patrones de bugs recurrentes, paridad de los seis idiomas, batería de tests completa. El nivel de exigencia no depende ni de la vigilancia del momento ni de la buena voluntad de la IA.
- **Una revisión que decide.** Nada entra sin un ciclo impuesto — análisis de impacto, propuesta, validación explícita, implementación, verificación. La IA propone, el humano decide; las decisiones estructurantes se registran e indexan, para que cada « porqué » sobreviva a su autor.
- **Auditorías que incomodan.** A intervalos regulares, el sistema entero se reexamina de forma contradictoria — hallazgos verificados con pruebas, falsos positivos eliminados, remediación planificada por olas. Es lo que detiene la deriva lenta que ninguna revisión cotidiana detecta.

> La velocidad viene de la IA. La calidad viene del marco. Y el marco es un trabajo de dirección.

## 4. Los arbitrajes

Tres decisiones estructurantes, entre las 266 documentadas:

**Soberanía y reversibilidad — ninguna dependencia irreversible de proveedor.** Los modelos de IA (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, modelos locales vía Ollama) están detrás de una abstracción única: cada uso puede cambiar de proveedor por configuración, con comparación de costes. Mismo principio del lado del negocio: Google, Apple y Microsoft son intercambiables por categoría funcional. El alojamiento está íntegramente controlado; los datos personales están cifrados y permanecen en la infraestructura.

**Economía de la IA — el coste por petición es un criterio de diseño.** Dos modos de ejecución coexisten: un pipeline determinista y económico para las peticiones corrientes, un modo agente autónomo para las exploratorias — la diferencia de consumo medida va de 1 a 4-8, con servicio equivalente en los casos estándar. Cada llamada se cuenta por token, se valora en euros, se agrega por usuario y por modelo, se gobierna por cuotas.

**Control del riesgo — ninguna acción irreversible sin validación humana.** Seis niveles de control humano, graduados según la sensibilidad de la acción — de la clarificación a la confirmación de las operaciones destructivas. El comportamiento en caso de interrupción está especificado y probado: una validación pendiente sobrevive a los reinicios, sin pérdida ni doble ejecución.

## 5. La explotación

Un sistema que se pilota con instrumentos:

- **Observabilidad**: veintiséis paneles — salud aplicativa, compromisos de servicio, costes de IA, comportamiento de los agentes, infraestructura. Más de 490 métricas; logs estructurados centralizados con filtrado de datos personales; trazado distribuido de extremo a extremo. Unos cuarenta procedimientos de explotación escritos — diagnóstico, remediación, restauración. Y el asistente lee él mismo esa telemetría: autocomprobación periódica, una memoria de incidentes diagnosticados sobre esas mismas procedimientos, y respuestas que esquivan una avería conocida. Y un diagnóstico muestra las evidencias de las que nació.
- **Entrega**: despliegue contenerizado, migraciones de esquema automatizadas, imágenes publicadas para dos arquitecturas de hardware (amd64/arm64).
- **Costes**: infraestructura frugal por elección — unos 150 € de hardware, cero licencias, bloques open source dimensionados a la necesidad real.
- **Conformidad**: seguridad revisada punto de acceso por punto de acceso; cifrado de los datos personales; ciclo de vida de las cuentas alineado con el RGPD.

## 6. La prueba

El nivel anunciado en este documento resulta de una auditoría técnica completa: 24 perímetros calificados, cada hallazgo verificado en el código y contraverificado para eliminar los falsos positivos. La auditoría aplica el método del propio proyecto — conducida con herramientas de IA, en postura contradictoria, cada conclusión anclada en una prueba contraverificada. Última evaluación: **8,3/10**, con un perfil asumido. El informe completo — cuadro de calificaciones, método, hallazgos abiertos y el protocolo para reproducirlo — es público: [informe de auditoría completo](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md).

**Puntos fuertes confirmados:**

- Capa de datos sólida: integridad referencial completa, migraciones sin ruptura, accesos concurrentes controlados.
- Observabilidad y herramientas de calidad completas, y realmente utilizadas a diario.
- Trazabilidad de las decisiones y disciplina de entrega mantenidas durante toda la duración.

**Lo que queda por hacer — conocido, planificado:**

- Copias de seguridad: cifrado y copias externas — la automatización diaria ya está en producción y verificada.
- Alertas: recalibración de los umbrales del parque histórico — el núcleo crítico está activo y probado de extremo a extremo, correo incluido.
- Continuación de la descomposición de los componentes más densos, ahora guiada por la medición (complejidad, acoplamiento) — los principales monolitos del backend están tratados.

El plan de acción está organizado en olas, cada una con criterios de salida medibles. Es la forma de rendir cuentas de este proyecto: no un nivel proclamado, un nivel medido — desviaciones incluidas.

Esta exigencia tiene una consecuencia que el proyecto aprendió a su costa: **una suite de pruebas en verde no demuestra que una función sirva**. Demuestra que lo probado se comporta como está escrito. Los defectos que sobreviven a las barreras son precisamente aquellos por los que nunca se les preguntó — una capacidad que nadie invoca, una cifra que nadie suma, una guardia que reconoce un nombre en lugar de un mecanismo.

De ahí una regla de trabajo: **nada se da por bueno antes de haber corrido**, sobre datos reales y por el camino que recorre la persona usuaria. Un componente puede ser correcto y su página estar vacía; un contador puede ser exacto y su pregunta equivocada. Cada entrega termina por tanto con una revisión adversarial, hecha en frío, cuyo objeto no es pasar las pruebas sino buscar lo que no cubren.

Lo que esa revisión produce no se detiene en la corrección. Cada defecto hallado deja tras de sí una **guardia estructural** — una comprobación al arrancar, un invariante verificado de continuo, una prueba que falla si reaparece toda la clase del problema. Es la única forma de progreso que sobrevive a quien la escribió: una corrección protege una línea, una guardia protege la regla.

---

## 7. Convicciones

Lo que esta experiencia cambia en una práctica de dirección:

- **El desarrollo asistido por IA se despliega como un dispositivo de gestión, no como una herramienta.** Las ganancias de productividad son reales e importantes; solo duran si el marco — referencial, controles, revisión, auditoría — está instalado antes de la generalización. Es en ese orden en el que hay que introducirlo en una organización.
- **La gobernanza económica de la IA se juega en el diseño de los usos.** Dos arquitecturas que prestan el mismo servicio pueden diferir en un factor de 4 a 8 en consumo: esa elección pertenece a la dirección técnica, aguas arriba — el control de la factura siempre llega demasiado tarde.
- **Entre la prohibición general y la confianza ciega, existe una vía gobernable.** El control humano graduado se especifica, se prueba y se audita; es el enfoque que dibujan las exigencias regulatorias, y es operativo desde ya.
- **Un directivo que practica arbitra mejor.** Hacer o mandar hacer, deuda aceptable o no, promesa de proveedor creíble o no — estas decisiones ganan en acierto cuando se ha probado la materia. Este proyecto es una forma de mantener esa proximidad con el terreno.

*Proyecto personal, llevado a cabo fuera de toda actividad profesional. Cifras procedentes de la auditoría técnica de julio de 2026 — tests ejecutados, mediciones efectuadas sobre el código, hallazgos contraverificados. Repositorio: [github.com/jgouviergmail/LIA-Assistant](https://github.com/jgouviergmail/LIA-Assistant).*
