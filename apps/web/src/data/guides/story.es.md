# Dirigir una IA que programa

> Informe de experiencia — un sistema completo, del diseño a la producción.

**Versión**: 2.3
**Fecha**: 2026-10-04
**Aplicación**: LIA v2.6.0
**Licencia**: AGPL-3.0 (Open Source)

---

## 1. Lo esencial

LIA es un asistente de IA multiagente completo — conectores de negocio, voz, memoria, conexiones entre usuarios, seis idiomas — diseñado, desarrollado y operado en producción de forma continua, como proyecto personal.

La casi totalidad del código fue escrita por una IA, bajo dirección humana: un referencial de ingeniería escrito, controles automáticos bloqueantes, revisión sistemática, auditorías recurrentes. El resultado está medido: **8,3/10** en la auditoría técnica sobre 24 perímetros. El repositorio es open source; las conclusiones de la auditoría — fortalezas y debilidades — se asumen y se resumen en este documento.

| Indicador | Valor |
| --- | --- |
| Código escrito por una IA — dirigida, encuadrada, controlada | **≈ 100 %** |
| Líneas de código fuente (sin tests) — 55 dominios funcionales | **820.000+** |
| Tests automatizados, ejecutados en cada commit y entrega | **51.000+** |
| Decisiones de arquitectura documentadas (ADR) | **333** |
| Versiones entregadas a ritmo regular | **277** |
| Idiomas, paridad verificada automáticamente | **6** |
| Auditoría técnica sobre 24 perímetros | **8,3/10** |

Convicción de experiencia: el desarrollo asistido por IA es industrializable hoy. El factor limitante no es la herramienta — es el marco de dirección que se le da.

La misma disciplina rige dentro del producto. Una pequeña decisión de modelo puede ayudar a elegir una ruta o un formato, pero LIA limita las opciones, mide el coste y conserva la autoridad para comprobar y confirmar el resultado. Las decisiones nativas opcionales amplían este método sin convertir la confianza del modelo en permiso.

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

Varios agentes pueden trabajar a la vez en el mismo repositorio — dos familias distintas de herramientas, cada una en su propio árbol de trabajo. La regla es la misma que para el código: nada se consolida sobre la base de un resumen. Cada archivo se atribuye a su autor por su huella y por el registro del agente, cada fusión se reproduce en un árbol aislado y luego pasa por todos los controles, y una copia de seguridad precede a cada cambio.

## 4. Los arbitrajes

Tres decisiones estructurantes, entre las 333 documentadas:

**Soberanía y reversibilidad — ninguna dependencia irreversible de proveedor.** Los modelos de IA (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, modelos locales vía Ollama) están detrás de una abstracción única: cada uso puede cambiar de proveedor por configuración, con comparación de costes. Mismo principio del lado del negocio: Google, Apple y Microsoft son intercambiables por categoría funcional. El autoalojamiento te da control del servidor; los datos de la cuenta se guardan en la instancia y las credenciales de los conectores están cifradas. Los servicios remotos que eliges siguen recibiendo los datos necesarios para su parte de la solicitud.

**Economía de la IA — el coste por petición es un criterio de diseño.** Dos modos de ejecución coexisten: un pipeline determinista y económico para las peticiones corrientes, un modo agente autónomo para las exploratorias — la diferencia de consumo medida va de 1 a 4-8, con servicio equivalente en los casos estándar. Cada llamada se cuenta por token, se valora en euros, se agrega por usuario y por modelo, se gobierna por cuotas. Incluso una notificación de dos frases se pide sin razonamiento, porque un modelo que razona por defecto factura su razonamiento dentro del presupuesto de la respuesta. Y el modo agente solo lleva consigo las herramientas que la pregunta reclama — elegidas por relevancia, nunca por orden de llegada —, porque ochenta esquemas de herramientas pesaban lo esencial de una primera llamada sin contarse. Y la cuenta sale exacta: cada llamada se valora al precio que el proveedor factura de verdad — tarifas releídas en sus páginas, escritura de caché a su precio, horas valle con sus días.

**Control del riesgo — ninguna acción irreversible sin validación humana.** Seis niveles de control humano, graduados según la sensibilidad de la acción — de la clarificación a la confirmación de las operaciones destructivas. El comportamiento en caso de interrupción está especificado y probado: una validación pendiente sobrevive a los reinicios, sin pérdida ni doble ejecución. Varias acciones en una misma petición se presentan una a una, cada una en su tarjeta, y el informe dice qué se hizo y para quién. El teléfono sigue la misma línea: la tarjeta protege a un tercero, así que cuando LIA llama a la propia persona — a un número declarado y verificado con un código leído en voz alta — la tarjeta es la persona; al teléfono — como en una sesión de voz live del navegador, con la clave propia de Gemini, OpenAI o ElevenLabs de la persona — el modo es su elección: la voz confía cada petición al chat en cuanto se dice, con sus confirmaciones, o lee sola y no actúa sobre nada; y lo que corre con la clave propia del proveedor se factura allí, se muestra una vez, nunca se cuenta aquí. Lo que la propia plataforma paga por la persona — una consulta de mapa durante una llamada, el tiempo del briefing, una foto mostrada — llega a su libro, sea cual sea el camino. Lo que envía un desconocido — un correo, su adjunto — sigue siendo un dato que leer, nunca una instrucción que seguir. Y un script que la asistente escribe llega a la web por una sola puerta, las claves de la persona cambiadas fuera de él — un host que nadie permitió se pregunta antes: con los datos, sin ellos, o nada. Y cuando el agente autónomo no puede obtener lo que se le pide, lo dice — con lo que intentó — en lugar de rellenar el hueco. Lo que debe ser exacto — un importe, una duración, una conversión — lo calcula una herramienta, nunca lo estima el modelo. Y lo que sale sin confirmación solo se dirige a la propia persona — un correo a uno mismo, una llamada a su número verificado —: el destinatario no es allí un parámetro, así que nada puede desviarlo. Por último, una competencia escrita fuera — tomada de una biblioteca pública o de un plugin — trabaja aparte: nunca los conectores de la persona, la red solo hacia los hosts permitidos, y una competencia que escribe la IA solo entra en su espacio con el clic de la persona.

## 5. La explotación

Un sistema que se pilota con instrumentos:

- **Observabilidad**: treinta y un paneles — salud aplicativa, compromisos de servicio, costes de IA, comportamiento de los agentes, infraestructura. Más de 600 métricas; logs estructurados centralizados; trazado distribuido de extremo a extremo — logs, métricas y trazas solo guardan hechos, nunca las palabras ni los nombres de las personas. Unos cuarenta procedimientos de explotación escritos — diagnóstico, remediación, restauración. Y el asistente lee él mismo esa telemetría: autocomprobación periódica, una memoria de incidentes diagnosticados sobre esas mismas procedimientos, y respuestas que esquivan una avería conocida. Y un diagnóstico muestra las evidencias de las que nació. Y los instrumentos llegan hasta los procesos: cada worker de la API publica lo que retiene en memoria, de modo que un total de contenedor se lee proceso a proceso.
- **Entrega**: despliegue contenerizado, migraciones de esquema automatizadas, imágenes publicadas para dos arquitecturas de hardware (amd64/arm64).
- **Cadena de suministro**: cada pieza del servidor fijada por su huella e inventariada con cada versión; una vigilancia semanal lee los avisos de seguridad que publica cada dependencia — incluidos los que ninguna base pública recoge — y una actualización espera un plazo de prudencia, sin retroceder nunca; cada versión se instala en máquinas vírgenes antes de publicarse.
- **Costes**: infraestructura frugal por elección — unos 150 € de hardware, cero licencias, bloques open source dimensionados a la necesidad real.
- **Protección de datos**: seguridad revisada punto de acceso por punto de acceso; credenciales de los conectores y claves de proveedores cifradas; exportación y eliminación de la cuenta. Las obligaciones del RGPD también dependen de cómo se opere la instancia y de los proveedores elegidos.

El producto hace visibles sus decisiones técnicas a escala humana. La conversación acompaña a una persona entre dispositivos sin interrumpir su lectura; la radio empieza cuando decide escuchar y muestra las fuentes y el coste de las noticias. La vida de un archivo generado puede prolongarse por decisión propia. El trabajo programado y las comprobaciones de condiciones tienen relojes distintos. Son promesas observables, respaldadas por fuentes, límites y pruebas, en lugar de afirmar que una asistente adivina lo que alguien desea.

La misma regla vale para lo que aún no está a la altura. La palabra de activación «Dis LIA» es un pequeño modelo entrenado sin conexión y medido en un banco cuyos umbrales se publican antes del entrenamiento: el modelo francés aún no los alcanza, así que se entrega marcado como **beta**, y el producto lo dice, en lugar de bajar el listón para poder escribir «terminado». Una sesión de voz que se duerme con un silencio no cuesta nada, y solo la persona la termina.

Esta disciplina también se aplica a una presencia visible. Un rostro experimental de Simli es una elección explícita con la clave de la persona, conectado a la voz existente con una sola salida audible. Una sesión abierta consume el plan personal durante los silencios; la espera de Live la cierra. La presentación mantiene pendiente la validación multimedia y móvil hasta que las pruebas reales la acrediten. La misma precisión gobierna el gasto: cada intento de pago al proveedor conserva su tarifa, y su uso conocido sobrevive al fallo, la cancelación o el reintento.

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

Esta exigencia tiene una consecuencia que el proyecto aprendió a su costa: **una suite de pruebas en verde no demuestra que una función sirva**. Demuestra que lo probado se comporta como está escrito. Los defectos que sobreviven a las barreras son precisamente aquellos por los que nunca se les preguntó — una capacidad que nadie invoca, una cifra que nadie suma, una guardia que reconoce un nombre en lugar de un mecanismo. Casi nunca son errores de código: son preguntas que nunca se habían hecho.

De ahí una regla de trabajo: **nada se da por bueno antes de haber corrido**, sobre datos reales y por el camino que recorre la persona usuaria. Un componente puede ser correcto y su página estar vacía; un contador puede ser exacto y su pregunta equivocada. Cada entrega termina por tanto con una revisión adversarial, hecha en frío, cuyo objeto no es pasar las pruebas sino buscar lo que no cubren. Y los recorridos de la interfaz se ejecutan en Chromium en cada entrega, y luego cada semana en Firefox y WebKit, con una comprobación automática de accesibilidad: un motor de navegador más ve lo que los otros dejan pasar.

Lo que esa revisión produce no se detiene en la corrección. Cada defecto hallado deja tras de sí una **guardia estructural** — una comprobación al arrancar, un invariante verificado de continuo, una prueba que falla si reaparece toda la clase del problema. Es la única forma de progreso que sobrevive a quien la escribió: una corrección protege una línea, una guardia protege la regla.

---

## 7. Convicciones

Lo que esta experiencia cambia en una práctica de dirección:

- **El desarrollo asistido por IA se despliega como un dispositivo de gestión, no como una herramienta.** Las ganancias de productividad son reales e importantes; solo duran si el marco — referencial, controles, revisión, auditoría — está instalado antes de la generalización. Es en ese orden en el que hay que introducirlo en una organización.
- **La gobernanza económica de la IA se juega en el diseño de los usos.** Dos arquitecturas que prestan el mismo servicio pueden diferir en un factor de 4 a 8 en consumo: esa elección pertenece a la dirección técnica, aguas arriba — el control de la factura siempre llega demasiado tarde.
- **Entre la prohibición general y la confianza ciega, existe una vía gobernable.** El control humano graduado se especifica, se prueba y se audita; es el enfoque que dibujan las exigencias regulatorias, y es operativo desde ya.
- **Un directivo que practica arbitra mejor.** Hacer o mandar hacer, deuda aceptable o no, promesa de proveedor creíble o no — estas decisiones ganan en acierto cuando se ha probado la materia. Este proyecto es una forma de mantener esa proximidad con el terreno.

*Proyecto personal, llevado a cabo fuera de toda actividad profesional. Evaluación técnica de la auditoría de julio de 2026, con hallazgos contraverificados. Los recuentos estructurales siguen el repositorio; las líneas de código fuente se volvieron a medir el 2026-10-05. Repositorio: [github.com/jgouviergmail/LIA-Assistant](https://github.com/jgouviergmail/LIA-Assistant).*
