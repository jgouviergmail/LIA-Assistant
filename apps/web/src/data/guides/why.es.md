# LIA — El Asistente IA Personal Soberano

> **Your Life. Your AI. Your Rules.**

**Versión**: 2.0
**Fecha**: 2026-03-24
**Aplicación**: LIA v1.13.1
**Licencia**: AGPL-3.0 (Open Source)

---

## Tabla de contenidos

1. [El mundo ha cambiado](#1-el-mundo-ha-cambiado)
2. [La tesis de LIA](#2-la-tesis-de-lia)
3. [Soberanía: retomar el control](#3-soberanía-retomar-el-control)
4. [Transparencia radical: ver qué hace la IA y cuánto cuesta](#4-transparencia-radical-ver-qué-hace-la-ia-y-cuánto-cuesta)
5. [La profundidad relacional: más allá de la memoria](#5-la-profundidad-relacional-más-allá-de-la-memoria)
6. [La orquestación que funciona en producción](#6-la-orquestación-que-funciona-en-producción)
7. [El control humano como filosofía](#7-el-control-humano-como-filosofía)
8. [Actuar en su vida digital](#8-actuar-en-su-vida-digital)
9. [La proactividad contextual](#9-la-proactividad-contextual)
10. [La voz como interfaz natural](#10-la-voz-como-interfaz-natural)
11. [La apertura como estrategia](#11-la-apertura-como-estrategia)
12. [La inteligencia que se autooptimiza](#12-la-inteligencia-que-se-autooptimiza)
13. [El tejido: cómo todo se entrelaza](#13-el-tejido-cómo-todo-se-entrelaza)
14. [Lo que LIA no pretende ser](#14-lo-que-lia-no-pretende-ser)
15. [Visión: hacia dónde va LIA](#15-visión-hacia-dónde-va-lia)

---

## 1. El mundo ha cambiado

### 1.1. La era agéntica ha llegado

Estamos en marzo de 2026. El panorama de la inteligencia artificial no tiene nada que ver con el de hace dos años. Los grandes modelos de lenguaje ya no son simples generadores de texto — se han convertido en **agentes capaces de actuar**.

**ChatGPT** cuenta ahora con un modo Agente que combina navegación web autónoma (heredada de Operator), investigación en profundidad y conexión con aplicaciones de terceros (Outlook, Slack, Google apps). Puede analizar competidores y crear presentaciones, planificar compras y encargarlas, informar a un usuario sobre sus reuniones a partir de su calendario. Sus tareas se ejecutan en un ordenador virtual dedicado, y los usuarios de pago acceden a un auténtico ecosistema de aplicaciones integradas.

**Google Gemini Agent** se ha integrado profundamente en el ecosistema Google: Gmail, Calendar, Drive, Tasks, Maps, YouTube. Chrome Auto Browse permite a Gemini navegar por la web de forma autónoma — rellenar formularios, realizar compras, ejecutar flujos de trabajo de múltiples pasos. La integración nativa con Android a través de AppFunctions extiende estas capacidades a nivel del sistema operativo.

**Microsoft Copilot** se ha transformado en una plataforma agéntica empresarial con más de 1 400 conectores, soporte del protocolo MCP, coordinación multiagente y Work IQ — una capa de inteligencia contextual que conoce su rol, su equipo y su empresa. Copilot Studio permite crear agentes autónomos sin código.

**Claude** de Anthropic ofrece Computer Use para interactuar con interfaces gráficas, y un rico ecosistema MCP para conectar herramientas, bases de datos y sistemas de archivos. Claude Code actúa como un agente de desarrollo completo.

El mercado de agentes IA alcanza los 7 840 millones de dólares en 2025 con un crecimiento del 46 % anual. Gartner prevé que el 40 % de las aplicaciones empresariales integrarán agentes IA específicos para finales de 2026.

### 1.2. Pero el mundo tiene un problema

Detrás de esta efervescencia se esconde una realidad más matizada.

**Solo entre el 10 y el 15 % de los proyectos de IA agéntica llegan a producción.** La tasa de fallo en la coordinación entre agentes es del 35 %. Gartner advierte que más del 40 % de los proyectos de IA agéntica serán cancelados para finales de 2027, por falta de control sobre costes y riesgos. Los costes de LLM se disparan en los bucles agénticos descontrolados, el comportamiento no determinista convierte la depuración en una pesadilla, y las trazas de auditoría suelen brillar por su ausencia.

Y sobre todo: **estos potentes asistentes son todos servicios cloud propietarios.** Sus correos electrónicos, su agenda, sus contactos, sus documentos — todo transita por los servidores de Google, Microsoft u OpenAI. La contrapartida de la comodidad es la cesión de sus datos más íntimos a empresas cuyo modelo de negocio se basa en la explotación de esos datos. El precio de la suscripción no es el precio real: **sus datos personales son el producto.**

Y cuando cambia de opinión, cuando quiere irse, su memoria, sus preferencias, su historial — todo queda prisionero de la plataforma. El lock-in es total.

### 1.3. Una pregunta fundamental

Es en este contexto donde LIA plantea una pregunta simple pero radical:

> **¿Es posible beneficiarse del poder de los agentes IA sin renunciar a la soberanía digital?**

La respuesta es sí. Y esa es toda la razón de ser de LIA.

---

## 2. La tesis de LIA

### 2.1. Lo que LIA no es

LIA no es un competidor frontal de ChatGPT, Gemini o Copilot. Pretender rivalizar con los presupuestos de investigación de Google, Microsoft u OpenAI sería una impostura.

LIA tampoco es un wrapper — una interfaz que oculta un único LLM detrás de una fachada atractiva.

### 2.2. Lo que LIA es

LIA es un **asistente IA personal soberano**: un sistema completo, open source, autoalojable, que orquesta de forma inteligente los mejores modelos de IA del mercado para actuar en su vida digital — bajo su control total, en su propia infraestructura.

Es una tesis en cinco puntos:

1. **La soberanía**: sus datos permanecen en su casa, en su servidor, incluso en un simple Raspberry Pi
2. **La transparencia**: cada decisión, cada coste, cada llamada LLM es visible y auditable
3. **La profundidad relacional**: una comprensión psicológica y emocional que va más allá de la simple memoria factual
4. **La fiabilidad en producción**: un sistema que ha resuelto los problemas que el 90 % de los proyectos agénticos no superan
5. **La apertura radical**: ningún lock-in, 7 proveedores de IA intercambiables, estándares abiertos

Estos cinco puntos no son funcionalidades de marketing. Son **decisiones arquitectónicas profundas** que atraviesan cada línea de código, cada decisión de diseño, cada compromiso técnico documentado en 59 Architecture Decision Records.

### 2.3. El sentido profundo

La convicción detrás de LIA es que el futuro de la IA personal no pasará por la sumisión a un gigante del cloud, sino por la **apropiación**: el usuario debe poder poseer su asistente, comprender su funcionamiento, controlar sus costes y hacerlo evolucionar según sus necesidades.

La IA más potente del mundo no sirve de nada si no puede confiar en ella. Y la confianza no se decreta — se construye mediante la transparencia, el control y la experiencia repetida.

---

## 3. Soberanía: retomar el control

### 3.1. El autoalojamiento como acto fundacional

LIA funciona en producción sobre un **Raspberry Pi 5** — un ordenador de placa única de 80 euros. Es una elección deliberada, no una limitación. Si un asistente IA completo con 15 agentes especializados, una pila de observabilidad y un sistema de memoria psicológica puede funcionar en un microservidor ARM, entonces la soberanía digital ya no es un privilegio empresarial — es un derecho accesible para todos.

Las imágenes Docker multiarquitectura (amd64/arm64) permiten el despliegue en cualquier infraestructura: un NAS Synology, un VPS de 5 euros al mes, un servidor empresarial o un clúster Kubernetes.

### 3.2. Sus datos, su base de datos

Cuando utiliza ChatGPT, sus conversaciones se almacenan en los servidores de OpenAI. Cuando activa la memoria de Gemini, sus recuerdos viven en Google. Cuando Copilot indexa sus archivos, transitan por Microsoft Azure.

Con LIA, todo reside en **su** PostgreSQL:

- Sus conversaciones y su historial
- Su memoria a largo plazo y su perfil psicológico
- Sus espacios de conocimiento (RAG)
- Sus diarios personales
- Sus preferencias y configuraciones

En cualquier momento puede exportar, respaldar, migrar o eliminar la totalidad de sus datos. El RGPD no es una restricción para LIA — es una consecuencia natural de la arquitectura.

### 3.3. La libertad de elegir IA

ChatGPT le vincula a OpenAI. Gemini a Google. Copilot a Microsoft.

LIA le conecta a **7 proveedores simultáneamente**: OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen y Ollama. Y puede combinarlos: usar OpenAI para la planificación, Anthropic para la respuesta, DeepSeek para las tareas de fondo — configurando cada nodo del pipeline de forma independiente desde una interfaz de administración.

Esta libertad no es solo una cuestión de coste o rendimiento. Es un **seguro contra la dependencia**: si un proveedor cambia sus tarifas, degrada su servicio o cierra su API, usted cambia con un solo clic.

---

## 4. Transparencia radical: ver qué hace la IA y cuánto cuesta

### 4.1. El problema de la caja negra

Cuando ChatGPT Agent ejecuta una tarea, usted ve el resultado. Pero ¿cuántas llamadas LLM fueron necesarias? ¿Qué modelos se utilizaron? ¿Cuántos tokens? ¿Qué coste? ¿Por qué esa decisión y no otra? No lo sabe. El sistema es una caja negra.

Esta opacidad no es neutral. Una suscripción de 20 o 200 dólares al mes crea la ilusión de gratuidad: nunca ve el coste real de sus interacciones. Esto fomenta el uso indiscriminado y priva al usuario de toda palanca de optimización.

### 4.2. La transparencia como valor fundamental

LIA adopta el enfoque opuesto: **todo es visible, todo es auditable**.

**El panel de depuración** — accesible desde la interfaz del chat — expone en tiempo real para cada conversación:

| Categoría                  | Lo que usted ve                                                                                                |
| -------------------------- | -------------------------------------------------------------------------------------------------------------- |
| **Análisis de intención**  | Cómo el enrutador clasificó su mensaje, con la puntuación de confianza                                         |
| **Pipeline de ejecución**  | El plan generado, las oleadas de ejecución paralela, las llamadas a herramientas con sus entradas/salidas      |
| **Pipeline LLM**           | Cada llamada LLM y embedding en orden cronológico: modelo, duración, tokens (entrada/caché/salida), coste      |
| **Contexto y memoria**     | Qué recuerdos se inyectaron, qué documentos RAG, qué perfil de intereses                                      |
| **Inteligencia**           | Los aciertos de caché, los patrones aprendidos, las expansiones semánticas                                     |
| **Diarios personales**     | Las notas inyectadas con su puntuación de relevancia, las extracciones en segundo plano                        |
| **Ciclo de vida**          | La temporización exacta de cada fase de la solicitud                                                           |

**El seguimiento de costes** es granular al céntimo: cada mensaje muestra su coste en tokens y en euros. El usuario puede exportar su consumo en CSV. El administrador dispone de dashboards en tiempo real con indicadores por usuario, cuotas configurables (tokens, mensajes, coste) por periodo y globales.

### 4.3. Por qué esto lo cambia todo

La transparencia no es un capricho para técnicos. Cambia la relación fundamental entre el usuario y su asistente:

- Usted **comprende** por qué LIA eligió un enfoque en lugar de otro
- Usted **controla** sus costes y puede optimizar (modelo más económico para el enrutamiento, más potente para la respuesta)
- Usted **detecta** los problemas (un plan que entra en bucle, una caché que no funciona, una memoria que contamina)
- Usted **confía** porque puede verificar, no porque le pidan que crea

---

## 5. La profundidad relacional: más allá de la memoria

### 5.1. Lo que hacen los demás

Los grandes asistentes disponen todos de sistemas de memoria que progresan rápidamente. ChatGPT retiene los hechos importantes, organiza automáticamente los recuerdos por prioridad, y GPT-5 comprende ahora el tono y la intención emocional. Gemini Personal Intelligence (gratuito desde marzo de 2026) accede a Gmail, Photos, Docs y YouTube para construir un contexto rico. Copilot utiliza Work IQ para comprender su rol, su equipo y sus hábitos profesionales.

Estos sistemas son potentes y mejoran constantemente. Pero su enfoque de la memoria sigue siendo esencialmente **factual y contextual**: retienen sus preferencias, sus datos personales y sus patrones de interacción. La comprensión emocional de GPT-5, por ejemplo, es implícita — emerge del modelo — pero no está estructurada, ponderada ni es explotable de forma programática.

### 5.2. Lo que hace LIA

LIA construye algo fundamentalmente diferente: un **perfil psicológico** del usuario.

Cada recuerdo no es un simple par clave-valor. Lleva consigo:

- Un **peso emocional** (-10 a +10): ¿este tema es fuente de alegría, ansiedad, dolor?
- Una **puntuación de importancia**: ¿hasta qué punto esta información es estructurante para la persona?
- Un **matiz de uso**: ¿cómo utilizar esta información de manera benevolente y apropiada?
- Una **categoría psicológica**: preferencia, dato personal, relación, sensibilidad, patrón de comportamiento

No se trata de psicología superficial. Es un sistema de extracción automática que analiza cada conversación a través del prisma de la personalidad activa del asistente, identifica las informaciones psicológicamente significativas y las almacena con su contexto emocional.

**Ejemplo concreto**: si usted menciona de pasada que su madre está enferma, LIA no almacena simplemente "madre enferma". Registra una sensibilidad con un peso emocional fuertemente negativo, un matiz de uso que prescribe no abordar nunca el tema a la ligera, y una categoría "relación/familia" que estructura la información en su perfil.

### 5.3. La seguridad emocional

LIA integra una **directiva de peligro emocional**. Cuando un recuerdo asociado a una fuerte carga emocional negativa (peso <= -5) se activa, el sistema pasa a modo protector con cuatro prohibiciones absolutas:

1. Nunca bromear sobre el tema
2. Nunca minimizar
3. Nunca comparar con otras situaciones
4. Nunca banalizar

Hasta donde sabemos, este tipo de mecanismo de protección emocional adaptativa no es habitual en los asistentes IA de consumo, que generalmente tratan todos los temas con la misma neutralidad. LIA adapta su comportamiento a la realidad emocional de la persona a la que acompaña.

### 5.4. Los diarios de a bordo: cuando el asistente reflexiona

LIA integra un mecanismo original: sus **diarios de a bordo** (Personal Journals).

El asistente lleva sus propias reflexiones, organizadas en cuatro temas: autorreflexión, observaciones sobre el usuario, ideas y análisis, aprendizajes. Estas notas están redactadas en primera persona, matizadas por la personalidad activa, e influyen de manera concreta en las respuestas futuras.

No es una memoria más. Es una forma de **introspección artificial** — el asistente que reflexiona sobre sus interacciones, anota sus propios aprendizajes, desarrolla sus propias perspectivas. Cuando ha escrito "el usuario prefiere las explicaciones concisas en temas técnicos", esa observación influye orgánicamente en sus respuestas futuras, sin ninguna regla codificada de forma rígida.

Los diarios se activan mediante dos mecanismos: extracción posconversación (después de cada intercambio) y consolidación periódica (cada 4 horas, revisión y reorganización de las notas). Un **guardia semántica de deduplicación** garantiza que el diario se mantenga denso en lugar de repetitivo: cuando una nueva idea es demasiado similar a una nota existente, el sistema enriquece la entrada existente en lugar de crear un duplicado. El usuario mantiene el control total: lectura, edición, eliminación, activación/desactivación.

### 5.5. El sistema de intereses

En paralelo, LIA desarrolla un **sistema de aprendizaje de centros de interés**: mediante análisis bayesiano de las consultas, detecta progresivamente los temas que le importan y puede, a la larga, enviarle proactivamente información relevante — un artículo, una noticia, un análisis — sobre esos temas.

### 5.6. La búsqueda híbrida

Todo este sistema de memoria se apoya en una **búsqueda híbrida** que combina similitud semántica (pgvector) y correspondencia de palabras clave (BM25). Este enfoque dual ofrece una precisión superior a la de cada método por separado: la semántica comprende el sentido, BM25 captura los nombres propios y los términos exactos.

---

## 6. La orquestación que funciona en producción

### 6.1. El verdadero desafío de la IA agéntica

La promesa agéntica es seductora: un asistente que planifica, ejecuta y sintetiza. La realidad es brutal: 35 % de tasa de fallo en la coordinación, costes explosivos por bucles descontrolados, depuración casi imposible debido al no determinismo.

LIA no pretende haber resuelto la IA agéntica en general. Pero ha resuelto **su** problema específico: orquestar 15 agentes especializados de manera fiable, económica y observable en producción, sobre hardware modesto.

### 6.2. Cómo funciona

Cuando envía un mensaje, este atraviesa un pipeline en 5 fases:

**Fase 1 — Comprender**: El enrutador analiza su mensaje en unos cientos de milisegundos y decide si se trata de una conversación simple o de una solicitud que requiere acciones. El analizador de consultas identifica los dominios implicados (correo, calendario, meteorología...) y un enrutador semántico afina la detección gracias a embeddings locales (+48 % de precisión).

**Fase 2 — Planificar**: Para las solicitudes complejas, un planificador inteligente genera un plan de ejecución estructurado — un árbol de dependencias con etapas, condiciones e iteraciones. Si un plan similar ya fue validado en el pasado, un aprendizaje bayesiano permite reutilizarlo directamente (bypass del LLM, ahorros masivos).

**Fase 3 — Validar**: El plan se somete a validación semántica y, si es necesario, a su aprobación mediante el sistema Human-in-the-Loop (véase la sección 7).

**Fase 4 — Ejecutar**: Las etapas del plan se ejecutan en paralelo cuando es posible, en secuencia cuando existen dependencias. Cada agente especializado gestiona su dominio (contactos, correos, calendario...) y los resultados alimentan las etapas siguientes.

**Fase 5 — Responder**: Un sistema de síntesis antialucinación en tres capas produce una respuesta fiel a los datos reales, sin invención ni extrapolación.

En segundo plano, tres procesos fire-and-forget se ejecutan sin impactar la latencia: extracción de memoria, extracción de diario, detección de intereses.

### 6.3. El control de costes

Donde la mayoría de los sistemas agénticos ven cómo sus costes se disparan, LIA ha desarrollado un conjunto de mecanismos de optimización que reducen el consumo de tokens en un 89 %:

- **Filtrado de catálogo**: solo las herramientas pertinentes para su consulta se presentan al LLM (96 % de reducción)
- **Aprendizaje de patrones**: los planes validados se memorizan y reutilizan (bypass del LLM si la confianza > 90 %)
- **Message Windowing**: cada nodo solo ve los N últimos mensajes necesarios (5/10/20 según el nodo)
- **Context Compaction**: resumen LLM de los mensajes antiguos cuando el contexto supera el umbral
- **Prompt Caching**: aprovechamiento de la caché nativa OpenAI/Anthropic (90 % de reducción)
- **Embeddings locales**: embeddings E5 ejecutados localmente (coste API cero, ~50 ms)

### 6.4. La observabilidad como red de seguridad

LIA dispone de una observabilidad nativa de nivel producción: 350+ métricas Prometheus, 18 dashboards Grafana, trazas distribuidas (Tempo), logging estructurado (Loki) y tracing LLM especializado (Langfuse). 59 Architecture Decision Records documentan cada decisión de diseño.

En un ecosistema donde el 89 % de los despliegues de agentes IA en producción implementan alguna forma de observabilidad, LIA va más allá con un panel de depuración integrado que hace accesibles estas métricas directamente en la interfaz de usuario, no en una herramienta de monitorización independiente.

---

## 7. El control humano como filosofía

### 7.1. Lo que hacen los demás

Gemini Agent "pide confirmación antes de las acciones críticas, como enviar un correo o realizar una compra". ChatGPT Operator "se niega a ejecutar ciertas tareas por razones de seguridad, como enviar correos y eliminar eventos". Es un enfoque binario: o la acción está permitida, o está prohibida.

### 7.2. El Human-in-the-Loop de LIA: 6 niveles de matiz

LIA no rechaza las acciones sensibles — se las **somete** con el nivel de detalle adecuado:

| Nivel                            | Desencadenante                             | Lo que usted ve                                        |
| -------------------------------- | ------------------------------------------ | ------------------------------------------------------ |
| **Aprobación de plan**           | Acciones destructivas o sensibles          | El plan completo con cada etapa detallada              |
| **Clarificación**                | Ambigüedad detectada                       | Una pregunta precisa para resolver la ambigüedad       |
| **Crítica de borrador**          | Email, evento, contacto a crear/modificar  | El borrador completo, editable antes del envío         |
| **Confirmación destructiva**     | Eliminación de 3+ elementos                | Advertencia explícita de irreversibilidad              |
| **Confirmación FOR_EACH**        | Operaciones masivas                        | Número de operaciones y naturaleza de cada acción      |
| **Revisión de modificación**     | Modificaciones sugeridas por la IA         | Comparación antes/después con resaltado                |

### 7.3. El matiz que lo cambia todo

La crítica de borrador ilustra esta filosofía. Cuando le pide a LIA que envíe un correo, ella no lo envía directamente (como haría un agente autónomo) ni tampoco se niega (como haría ChatGPT Operator). Le muestra el borrador completo con plantillas markdown adaptadas al dominio (correo, evento, contacto, tarea), emojis de campos, una comparación before/after para las modificaciones y una advertencia de irreversibilidad para las eliminaciones. Usted puede modificar, aprobar o rechazar.

Es la diferencia entre un agente que actúa en su lugar y un asistente que le **propone** y le deja decidir. La confianza no nace de la ausencia de riesgo — nace de la **visibilidad** sobre lo que va a ocurrir.

### 7.4. El feedback implícito

Cada aprobación o rechazo alimenta el sistema de aprendizaje de patrones. Si usted aprueba sistemáticamente un tipo de plan, LIA aprende y propone con más confianza. El HITL no es solo una barrera de seguridad — es un mecanismo de **calibración continua** de la inteligencia del sistema.

---

## 8. Actuar en su vida digital

### 8.1. Tres ecosistemas, una interfaz

LIA se conecta a los tres grandes ecosistemas ofimáticos del mercado:

**Google Workspace** (OAuth 2.1 + PKCE): Gmail, Google Calendar, Google Contacts (14+ esquemas), Google Drive, Google Tasks — con cobertura CRUD completa.

**Microsoft 365** (OAuth 2.0 + PKCE): Outlook, Calendar, Contacts, To Do — cuentas personales y profesionales (Azure AD multitenant).

**Apple iCloud** (IMAP/SMTP, CalDAV, CardDAV): Apple Mail, Apple Calendar, Apple Contacts — para quienes viven en el ecosistema Apple.

Un principio de exclusividad mutua garantiza la coherencia: un solo proveedor activo por categoría (correo, calendario, contactos, tareas). Puede tener Google para el calendario y Microsoft para el correo.

### 8.2. Hogar conectado

LIA controla su iluminación Philips Hue mediante comandos en lenguaje natural: encender/apagar, ajustar brillo y colores, gestionar habitaciones y escenas. Conexión local (misma red) o cloud (OAuth2 Philips Hue).

### 8.3. Navegación web y extracción

Un agente de navegación autónomo (Playwright/Chromium headless) puede navegar por sitios web, hacer clic, rellenar formularios, extraer datos de páginas JavaScript complejas — a partir de una simple instrucción en lenguaje natural. Un modo de extracción más simple convierte cualquier URL en texto Markdown utilizable.

### 8.4. Archivos adjuntos

Imágenes (análisis por modelo de visión) y PDF (extracción de texto) están soportados como archivos adjuntos, con compresión del lado del cliente y aislamiento estricto por usuario.

### 8.5. Espacios de conocimiento (RAG Spaces)

Cree bases documentales personales cargando sus documentos (15+ formatos: PDF, DOCX, PPTX, XLSX, CSV, EPUB...). Sincronización automática de carpetas de Google Drive con detección incremental. Búsqueda híbrida semántica + palabras clave. Y una base de conocimiento del sistema (119+ Q/A) permite a LIA responder a preguntas sobre sus propias funcionalidades.

---

## 9. La proactividad contextual

### 9.1. Más allá de la notificación

La proactividad de LIA no es un sistema de alertas configurado manualmente. Es un **juicio LLM contextualizado** que agrega en paralelo 7 fuentes de contexto — calendario, meteorología (con detección de cambios: inicio/fin de lluvia, caída de temperatura, alerta de viento), tareas, correos, intereses, memorias, diarios — y deja que un modelo de lenguaje decida si hay algo genuinamente útil que comunicar.

El sistema en dos fases separa la **decisión** (modelo económico, temperatura baja, salida estructurada: "notificar" o "no notificar") de la **generación** (modelo expresivo, personalidad del asistente, idioma del usuario).

### 9.2. Anti-spam por diseño

Cuota diaria configurable (1-8/día), ventana horaria personalizable, cooldown entre notificaciones, antirredundancia mediante inyección del historial reciente en el prompt de decisión, omisión si el usuario está en conversación activa. La proactividad es opt-in, cada parámetro es modificable, y la desactivación preserva los datos.

### 9.3. Iniciativa conversacional

Durante una conversación, LIA no se limita a responder la pregunta formulada. Después de cada ejecución, un **agente de iniciativa** analiza los resultados y verifica proactivamente la información conexa — si la meteorología anuncia lluvia el sábado, la iniciativa consulta el calendario para señalar posibles actividades al aire libre. Si un correo menciona una cita, verifica la disponibilidad. Totalmente guiado por prompt (sin lógica codificada de forma rígida), limitado a acciones de lectura, enriquecido por la memoria y los centros de interés del usuario.

### 9.4. Acciones programadas

Más allá de las notificaciones, LIA ejecuta acciones recurrentes programadas con gestión de zona horaria, reintentos automáticos y desactivación tras fallos consecutivos. Los resultados se notifican vía push (FCM), SSE y Telegram.

---

## 10. La voz como interfaz natural

### 10.1. Entrada de voz

**Push-to-Talk**: mantenga pulsado el botón del micrófono para hablar. Optimizado para móvil con anti-long-press, gestión de gestos táctiles, cancelación por deslizamiento.

**Palabra clave "OK Guy"**: detección manos libres ejecutada **íntegramente en su navegador** mediante Sherpa-onnx WASM — ningún sonido se transmite a un servidor mientras no se detecte la palabra clave. La transcripción utiliza Whisper (99+ idiomas, offline) respetando su idioma preferido.

**Optimizaciones de latencia**: reutilización del flujo del micrófono, preconexión WebSocket, configuración en paralelo — el retardo entre la detección de la palabra clave y el inicio de la grabación es de ~50-100 ms.

### 10.2. Salida de voz

Dos modos: Standard (Edge TTS, gratuito, alta calidad) y HD (OpenAI TTS o Gemini TTS, premium). Cambio automático de HD a Standard en caso de fallo.

---

## 11. La apertura como estrategia

### 11.1. Estándares abiertos, sin lock-in

| Estándar                         | Uso en LIA                                                                                  |
| -------------------------------- | ------------------------------------------------------------------------------------------- |
| **MCP** (Model Context Protocol) | Conexión de herramientas externas por usuario, con OAuth 2.1, prevención SSRF, rate limiting |
| **agentskills.io**               | Skills inyectables con progressive disclosure (L1/L2/L3), generador integrado               |
| **OAuth 2.1 + PKCE**             | Autenticación delegada para todos los conectores                                            |
| **OpenTelemetry**                | Observabilidad estandarizada                                                                |
| **AGPL-3.0**                     | Código fuente completo, auditable, modificable                                              |

### 11.2. MCP: extensibilidad sin límites

Cada usuario puede conectar sus propios servidores MCP, extendiendo las capacidades de LIA mucho más allá de las herramientas integradas. Las descripciones de dominio se generan automáticamente por LLM para un enrutamiento inteligente. Las MCP Apps permiten mostrar widgets interactivos (como Excalidraw para diagramas) directamente en el chat. El **modo iterativo (ReAct)** permite que los servidores con API complejas sean gestionados por un agente dedicado que primero lee la documentación y luego llama a las herramientas con los parámetros correctos — en lugar de precalcular todo en el plan estático.

### 11.3. Skills: competencias a medida

Los Skills (estándar agentskills.io) permiten inyectar instrucciones expertas. Un Skill de "briefing matutino" puede coordinar calendario, meteorología, correos y tareas en un solo comando determinista. El generador integrado le guía en la creación de Skills en lenguaje natural.

### 11.4. Multicanal

La interfaz web responsiva se complementa con una integración nativa de Telegram (conversación textual, mensajes de voz transcritos, botones HITL inline, notificaciones proactivas) y notificaciones push Firebase.

---

## 12. La inteligencia que se autooptimiza

### 12.1. El aprendizaje bayesiano de planes

Con cada plan validado y ejecutado con éxito, LIA registra el patrón. Una puntuación bayesiana calcula la confianza en cada patrón. Por encima del 90 % de confianza, el plan se reutiliza directamente sin llamada LLM — ahorros masivos de tokens y latencia. El sistema arranca con 50+ "golden patterns" predefinidos y se enriquece continuamente.

### 12.2. El enrutamiento semántico local

Embeddings multilingües E5 (100+ idiomas) ejecutados localmente en ~50 ms permiten un enrutamiento semántico que mejora la precisión de detección de intención en un 48 % respecto al enrutamiento puramente LLM — a coste cero.

### 12.3. La antialucinación en tres capas

El nodo de respuesta dispone de un sistema antialucinación en tres capas: formateo de datos con límites explícitos, directivas del sistema que imponen el uso exclusivo de datos verificados, y gestión explícita de los casos límite (rechazo, error, ausencia de resultados). El LLM está constreñido a sintetizar únicamente lo que proviene de los resultados reales de las herramientas.

---

## 13. El tejido: cómo todo se entrelaza

La potencia de LIA no reside en la suma de sus funcionalidades. Reside en su **entrelazamiento** — la manera en que cada subsistema refuerza a los demás para crear algo que supera la suma de las partes.

### 13.1. Memoria + Proactividad + Diarios

LIA no se limita a saber que usted tiene una reunión mañana. Gracias a su memoria, conoce su ansiedad respecto a ese tema. Gracias a sus diarios, ha anotado que las presentaciones cortas funcionan mejor con ese interlocutor. Gracias a su sistema de intereses, ha detectado un artículo pertinente. La notificación proactiva integra todas estas dimensiones en un mensaje personalizado, coherente y útil — no una alerta genérica.

### 13.2. HITL + Pattern Learning + Costes

Cada interacción HITL alimenta el aprendizaje. Su aprobación de un plan lo inscribe en la memoria bayesiana. La próxima vez, se reutilizará sin llamada LLM: mejor experiencia (más rápida), menor coste (menos tokens), mayor confianza (plan ya validado). El HITL no ralentiza el sistema — lo **acelera** con el tiempo.

### 13.3. RAG + Respuesta

Sus espacios de conocimiento enriquecen directamente las respuestas de LIA. Si ha cargado los procedimientos de su empresa y formula una pregunta sobre el proceso de validación, LIA busca en sus documentos e integra la información pertinente en su respuesta. Los costes de embedding se rastrean por documento y por consulta, visibles en el chat y en el dashboard.

### 13.4. Enrutamiento semántico + Filtrado de catálogo + Transparencia

El enrutamiento semántico local detecta los dominios pertinentes. El filtrado de catálogo reduce las herramientas presentadas al LLM en un 96 %. El panel de depuración le muestra exactamente esta selección. Resultado: planes más precisos, más económicos, que usted puede comprender y auditar.

### 13.5. Voz + Telegram + Web + Soberanía

La misma inteligencia es accesible a través de tres canales que se complementan: la web para las operaciones complejas, Telegram para la movilidad, la voz para el manos libres. Su memoria, sus diarios, sus preferencias le acompañan de un canal a otro — y todo permanece en su servidor.

---

## 14. Lo que LIA no pretende ser

### 14.1. LIA no es el "mejor chatbot"

Como generador de texto conversacional, GPT-5.4 o Claude Opus 4.6 utilizados a través de su interfaz nativa serán probablemente más fluidos que LIA — porque LIA no es un chatbot. Es un sistema de orquestación que utiliza estos modelos como componentes.

### 14.2. LIA no tiene los recursos de los GAFAM

El equipo de integración de Gemini con Google Workspace cuenta con miles de ingenieros y acceso directo a las APIs internas. LIA utiliza las mismas APIs públicas que cualquier desarrollador. La cobertura funcional nunca será idéntica.

### 14.3. LIA no es "plug and play"

El autoalojamiento tiene un precio: la configuración inicial, el mantenimiento del servidor, la gestión de las actualizaciones. LIA dispone de un sistema de configuración simplificado (`task setup` y luego `task dev`), pero no es tan sencillo como registrarse en chatgpt.com.

### 14.4. Por qué esta honestidad importa

Porque la confianza se construye sobre la verdad, no sobre el marketing. LIA sobresale allí donde ha elegido sobresalir: la soberanía, la transparencia, la profundidad relacional, la fiabilidad en producción y la apertura. En lo demás, se apoya en los mejores LLM del mercado — a los que orquesta en lugar de intentar reemplazarlos.

---

## 15. Visión: hacia dónde va LIA

### 15.1. La inteligencia emergente

La combinación memoria psicológica + diarios introspectivos + aprendizaje bayesiano + intereses + proactividad crea las condiciones de una forma de **inteligencia emergente**: con el paso de los meses, LIA desarrolla una comprensión cada vez más matizada de quién es usted, qué necesita y cómo presentárselo. No es inteligencia artificial general. Es una inteligencia **práctica y relacional**, al servicio de una persona concreta.

### 15.2. La arquitectura extensible

Cada componente está diseñado para la extensión sin reescritura:

- **Nuevos conectores** (Slack, Notion, Trello) mediante la abstracción por protocolo
- **Nuevos canales** (Discord, WhatsApp) mediante la arquitectura BaseChannel
- **Nuevos agentes** sin modificar el núcleo del sistema
- **Nuevos proveedores de IA** mediante la factory LLM
- **Nuevas herramientas MCP** por simple conexión del usuario

### 15.3. La convergencia

La visión a largo plazo de LIA es la de un **sistema nervioso digital personal**: un punto único que orquesta el conjunto de su vida digital, con la memoria de un asistente que le conoce desde hace años, la proactividad de un colaborador atento, la transparencia de una herramienta que usted comprende y la soberanía de un sistema que usted posee.

En un mundo donde la IA estará en todas partes, la pregunta ya no será "¿qué IA usar?" sino "**¿quién controla mi IA?**". LIA responde: usted.

---

## Conclusión: por qué existe LIA

LIA no existe porque al mundo le falten asistentes IA. Los hay de sobra. ChatGPT, Gemini, Copilot, Claude — cada uno es notable a su manera.

LIA existe porque al mundo le falta un asistente IA que sea **suyo**. Verdaderamente suyo. En su servidor, con sus datos, bajo su control, con una transparencia total sobre lo que hace y lo que cuesta, una comprensión psicológica que va más allá de los hechos, y la libertad de elegir qué modelo de IA lo anima.

No es un chatbot. No es una plataforma cloud. Es un **compañero digital soberano** — y es precisamente lo que faltaba.

**Your Life. Your AI. Your Rules.**

---

*Documento redactado sobre la base del código fuente de LIA v1.13.1, de 190+ documentos técnicos, de 63 ADRs, del changelog completo y de un análisis del panorama competitivo de IA de marzo de 2026. Todas las funcionalidades descritas están implementadas y son verificables en el código. Los datos de mercado provienen de Gartner, IBM y de las publicaciones oficiales de OpenAI, Google, Microsoft y Anthropic.*
