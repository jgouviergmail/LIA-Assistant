# LIA — El Asistente IA que te pertenece

> **Your Life. Your AI. Your Rules.**

**Versión** : 3.0
**Fecha** : 2026-04-08
**Aplicación** : LIA v1.14.5
**Licencia** : AGPL-3.0 (Open Source)

---

## Tabla de contenidos

1. [El contexto](#1-el-contexto)
2. [Administración sencilla](#2-administración-sencilla)
3. [Lo que LIA sabe hacer](#3-lo-que-lia-sabe-hacer)
4. [Un servidor para tus seres queridos](#4-un-servidor-para-tus-seres-queridos)
5. [Soberanía y frugalidad](#5-soberanía-y-frugalidad)
6. [Transparencia radical](#6-transparencia-radical)
7. [Profundidad emocional](#7-profundidad-emocional)
8. [Fiabilidad en producción](#8-fiabilidad-en-producción)
9. [Apertura radical](#9-apertura-radical)
10. [Visión](#10-visión)

---

## 1. El contexto

La era de los asistentes IA agénticos ha llegado. ChatGPT, Gemini, Copilot, Claude — cada uno ofrece un agente capaz de actuar en tu vida digital: enviar correos, gestionar tu agenda, buscar en la web, controlar tus dispositivos.

Estos asistentes son notables. Pero comparten un modelo común: tus datos viven en sus servidores, la inteligencia es una caja negra, y cuando te vas, todo se queda atrás.

LIA toma un camino distinto. No es un competidor frontal de los gigantes — es un **asistente IA personal que tú albergas, que tú entiendes y que tú controlas**. LIA orquesta los mejores modelos de IA del mercado, actúa en tu vida digital y lo hace con cualidades fundamentales que lo distinguen.

---

## 2. Administración sencilla

### 2.1. Un despliegue guiado, luego cero fricción

El auto-alojamiento tiene mala fama. LIA no pretende eliminar cada paso técnico: la configuración inicial — claves API, conectores OAuth, elección de infraestructura — requiere algo de tiempo y conocimientos básicos. Pero cada etapa está **documentada en detalle** en una guía de despliegue paso a paso.

Una vez terminada esa fase, **todo lo del día a día se gestiona desde una interfaz web intuitiva**. Sin terminal ni archivos de configuración.

### 2.2. Lo que cada usuario puede configurar

Cada usuario dispone de su propio espacio de configuración, organizado en dos pestañas:

**Preferencias personales:**

- **Conectores personales**: conecta tus cuentas de Google, Microsoft o Apple en pocos clics mediante OAuth — correo, calendario, contactos, tareas, Google Drive. O conecta Apple vía IMAP/CalDAV/CardDAV. Claves API para servicios externos (tiempo, búsqueda)
- **Personalidad**: elige entre las personalidades disponibles (profesor, amigo, filósofo, coach, poeta...) — cada una influye en el tono, el estilo y el comportamiento emocional de LIA
- **Voz**: configura el modo vocal — palabra clave de activación, sensibilidad, umbral de silencio, lectura automática de respuestas
- **Notificaciones**: gestiona las notificaciones push y los dispositivos registrados
- **Canales**: conecta Telegram para chatear y recibir notificaciones en el móvil
- **Generación de imágenes**: activa y configura la creación de imágenes por IA
- **Servidores MCP personales**: conecta tus propios servidores MCP para ampliar las capacidades de LIA
- **Apariencia**: idioma, zona horaria, tema (5 paletas, modo oscuro/claro), fuente (9 opciones), formato de visualización de respuestas (tarjetas HTML, HTML, Markdown)
- **Debug**: accede al panel de depuración para inspeccionar cada intercambio (si el administrador lo ha activado)

**Funcionalidades avanzadas:**

- **Psyche Engine**: ajusta los rasgos de personalidad (Big Five) que modulan la reactividad emocional de tu asistente
- **Memoria**: consulta, edita, fija o elimina los recuerdos de LIA — activa o desactiva la extracción automática de hechos
- **Diarios personales**: configura la extracción de introspecciones tras cada conversación y la consolidación periódica
- **Centros de interés**: define tus temas favoritos, configura la frecuencia de notificaciones, los horarios y las fuentes (Wikipedia, Perplexity, reflexión IA)
- **Notificaciones proactivas**: ajusta la frecuencia, la ventana horaria y las fuentes de contexto (calendario, tiempo, tareas, correos, intereses, memorias, diarios)
- **Acciones programadas**: crea automatizaciones recurrentes ejecutadas por el asistente
- **Skills**: activa o desactiva competencias expertas, crea tus propios Skills personales
- **Espacios de conocimiento**: carga tus documentos (PDF, Word, Excel, PowerPoint, EPUB, HTML y más de 15 formatos) o sincroniza una carpeta de Google Drive — indexación automática con búsqueda híbrida
- **Exportación de consumo**: descarga tus datos de consumo LLM y API en CSV

### 2.3. Lo que controla el administrador

El administrador accede a una tercera pestaña dedicada a la gestión de la instancia:

**Usuarios y accesos:**

- **Gestión de usuarios**: crear, activar o desactivar cuentas, visualizar los servicios conectados y las funcionalidades activadas por usuario
- **Límites de uso**: definir cuotas por usuario (tokens LLM, llamadas API, generaciones de imágenes) con seguimiento en tiempo real y bloqueo automático
- **Mensajes broadcast**: enviar mensajes importantes a todos los usuarios o a una selección, con fecha de expiración opcional
- **Exportación de consumo global**: exportar el consumo de todos los usuarios en CSV

**IA y conectores:**

- **Configuración LLM**: configurar las claves API de los proveedores (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, Ollama), asignar un modelo por rol en el pipeline, gestionar los niveles de razonamiento — claves almacenadas cifradas
- **Activación/desactivación de conectores**: activar o desactivar integraciones a nivel global (Google OAuth, Apple, Microsoft 365, Hue, tiempo, Wikipedia, Perplexity, Brave Search). La desactivación revoca las conexiones activas y notifica a los usuarios
- **Precios**: gestionar los precios por modelo LLM (coste por millón de tokens), por API de Google Maps (Places, Routes, Geocoding) y por generación de imagen — con historial de precios

**Contenido y extensiones:**

- **Personalidades**: crear, editar, traducir y eliminar las personalidades disponibles para todos los usuarios — definir la personalidad predeterminada
- **Skills del sistema**: gestionar las competencias expertas a escala de la instancia — importar/exportar, activar/desactivar, traducir
- **Espacios de conocimiento del sistema**: gestionar la base de conocimientos FAQ, supervisar el estado de la indexación y las migraciones de modelos
- **Voz global**: configurar el modo TTS predeterminado (estándar o HD) para todos los usuarios
- **Debug del sistema**: configuración de logs y diagnóstico

### 2.4. Un asistente, no un proyecto técnico

El objetivo de LIA no es convertirte en administrador de sistemas. Es ofrecerte la potencia de un asistente IA completo **con la sencillez de una aplicación de consumo**. La interfaz se puede instalar como una aplicación nativa en ordenador, tableta y smartphone (PWA), y todo está pensado para ser accesible sin conocimientos técnicos en el día a día.

---

## 3. Lo que LIA sabe hacer

LIA actúa de forma concreta en tu vida digital gracias a 19+ agentes especializados que cubren el conjunto de necesidades cotidianas: gestión de tus datos personales (correos, calendario, contactos, tareas, archivos), acceso a información externa (búsqueda web, tiempo, lugares, rutas), creación de contenido (imágenes, diagramas), control de tu hogar conectado, navegación web autónoma y anticipación proactiva de tus necesidades.

Tú eliges cómo razona LIA, mediante un simple toggle (⚡) en el encabezado del chat:

- **Modo Pipeline** (por defecto) — Una verdadera proeza de ingeniería: LIA planifica todos los pasos por adelantado, los valida semánticamente y ejecuta las herramientas en paralelo. Resultado: la misma potencia que un agente autónomo, pero consumiendo 4 a 8 veces menos tokens. El modo más económico y predecible.
- **Modo ReAct** (⚡) — El asistente razona paso a paso: llama a una herramienta, analiza el resultado y decide qué hacer después. Más autónomo, más adaptable, pero más costoso en tokens. Ideal para investigaciones exploratorias o preguntas complejas cuyo valor añadido justifica el costo.

### 3.1. Conversación natural

Habla con LIA como lo harías con un asistente humano — sin comandos que memorizar, sin sintaxis que respetar. LIA entiende y responde en más de 99 idiomas, con una interfaz disponible en 6 idiomas (francés, inglés, alemán, español, italiano, chino). Las respuestas se muestran en tarjetas visuales HTML interactivas, en HTML directo o en Markdown según tus preferencias.

### 3.2. Servicios conectados personales

- **Correo**: leer, buscar, redactar, enviar, responder, reenviar — vía Gmail, Outlook o Apple Mail
- **Calendario**: consultar, crear, modificar y eliminar eventos — vía Google Calendar, Outlook Calendar o Apple Calendar
- **Contactos**: buscar, crear y modificar contactos — vía Google Contacts, Outlook Contacts o Apple Contacts
- **Tareas**: gestionar tus listas de tareas — vía Google Tasks o Microsoft To Do
- **Archivos**: acceder a Google Drive para buscar y leer tus documentos
- **Hogar conectado**: controlar tu iluminación Philips Hue — encender/apagar, brillo, colores, escenas, gestión por habitación

### 3.3. Inteligencia web y entorno

- **Búsqueda web**: búsqueda multi-fuente (Brave Search, Perplexity, Wikipedia) para respuestas completas y con referencias
- **Tiempo**: condiciones actuales y previsiones a 5 días, con detección de cambios (inicio/fin de lluvia, bajada de temperatura, alertas de viento)
- **Lugares y comercios**: búsqueda de lugares cercanos con detalles, horarios y reseñas
- **Rutas**: cálculo de rutas multimodales (coche, a pie, bicicleta, transporte público) con geolocalización automática

### 3.4. Voz

LIA ofrece un modo vocal completo:

- **Push-to-Talk**: mantén pulsado el botón de micrófono para hablar, optimizado para móvil
- **Palabra clave "OK Guy"**: detección manos libres ejecutada **íntegramente en tu navegador** mediante Sherpa-onnx WASM — no se transmite ningún audio hasta que se detecta la palabra clave
- **Síntesis de voz**: modo estándar (Edge TTS, gratuito) o HD (OpenAI TTS / Gemini TTS)
- **Mensajes de voz en Telegram**: envía mensajes de audio, LIA los transcribe y responde

### 3.5. Creación y medios

- **Generación de imágenes**: crea imágenes a partir de descripciones textuales, edita fotos existentes
- **Diagramas Excalidraw**: genera diagramas y esquemas directamente en la conversación
- **Adjuntos**: añade fotos y PDF — LIA analiza el contenido visual y extrae el texto de los documentos
- **MCP Apps**: widgets interactivos directamente en el chat (formularios, visualizaciones, mini-aplicaciones)

### 3.6. Proactividad e iniciativa

LIA no se limita a responder — anticipa:

- **Notificaciones proactivas**: LIA cruza tus fuentes de contexto (calendario, tiempo, tareas, correos, intereses) y te avisa cuando es genuinamente útil — con un sistema anti-spam integrado (cuota diaria, ventana horaria, cooldown)
- **Iniciativa conversacional**: durante un intercambio, LIA verifica proactivamente información relacionada — si el tiempo anuncia lluvia el sábado, consulta tu calendario para señalar posibles actividades al aire libre
- **Centros de interés**: LIA detecta progresivamente los temas que te apasionan y puede enviarte contenido relevante
- **Subagentes**: para tareas complejas, LIA delega en agentes efímeros especializados que trabajan en paralelo

### 3.7. Navegación web autónoma

Un agente de navegación (Playwright/Chromium headless) puede navegar por sitios web, hacer clic, rellenar formularios y extraer datos de páginas dinámicas — a partir de una simple instrucción en lenguaje natural. Un modo de extracción simplificado convierte cualquier URL en texto utilizable.

### 3.8. Administración del servidor (DevOps)

Al instalar Claude CLI (Claude Code) directamente en el servidor, los administradores pueden diagnosticar su infraestructura en lenguaje natural desde el chat de LIA: consultar logs de Docker, verificar el estado de los contenedores, monitorizar el espacio en disco, analizar errores. Esta funcionalidad está reservada a las cuentas de administrador.

---

## 4. Un servidor para tus seres queridos

### 4.1. LIA es un servidor web compartido

A diferencia de los asistentes cloud personales (una cuenta = un usuario), LIA está diseñado como un **servidor centralizado** que despliegas una sola vez y compartes con tu familia, tus amigos o tu equipo.

Cada usuario dispone de su propia cuenta con:

- Su perfil, sus preferencias, su idioma
- **Su propia personalidad de asistente** con su estado de ánimo, sus emociones y su relación única — gracias al Psyche Engine, cada usuario interactúa con un asistente que desarrolla un vínculo emocional distinto
- Su memoria, sus recuerdos, sus diarios personales — totalmente aislados
- Sus propios conectores (Google, Microsoft, Apple)
- Sus espacios de conocimiento privados

### 4.2. Gestión de uso por usuario

El administrador mantiene el control del consumo:

- **Límites de uso** configurables por usuario: número de mensajes, tokens, coste máximo — por día, por semana, por mes o en acumulado global
- **Cuotas visuales**: cada usuario ve su consumo en tiempo real con indicadores claros
- **Activación/desactivación de conectores**: el administrador activa o desactiva las integraciones (Google, Microsoft, Hue...) a nivel de instancia

### 4.3. Tu IA familiar

Imagínalo: una Raspberry Pi en tu salón, y toda la familia disfrutando de un asistente IA inteligente — cada uno con su experiencia personalizada, sus recuerdos, su estilo de conversación, y un asistente que desarrolla su propia relación emocional con él. Todo bajo tu control, sin suscripción cloud, sin datos que se vayan a un tercero.

---

## 5. Soberanía y frugalidad

### 5.1. Tus datos se quedan contigo

Cuando usas ChatGPT, tus conversaciones viven en los servidores de OpenAI. Con Gemini, en los de Google. Con Copilot, en los de Microsoft.

Con LIA, **todo se queda en tu PostgreSQL**: conversaciones, memoria, perfil psicológico, documentos, preferencias. Puedes exportar, hacer copias de seguridad, migrar o eliminar la totalidad de tus datos en cualquier momento. El RGPD no es una restricción — es una consecuencia natural de la arquitectura. Los datos sensibles están cifrados, las sesiones aisladas, y el filtrado automático de información personal identificable (PII) está integrado.

### 5.2. Incluso una Raspberry Pi es suficiente

LIA funciona en producción sobre una **Raspberry Pi 5** — un ordenador de placa única de 80 euros. 19+ agentes especializados, una stack de observabilidad completa, un sistema de memoria psicológica, todo sobre un micro-servidor ARM. Las imágenes Docker multi-arquitectura (amd64/arm64) permiten el despliegue en cualquier hardware: NAS Synology, VPS a pocos euros al mes, servidor empresarial o cluster Kubernetes.

La soberanía digital ya no es un privilegio empresarial — es un derecho accesible para todos.

### 5.3. Optimizado para la frugalidad

LIA no solo funciona con hardware modesto — **optimiza activamente** su consumo de recursos de IA:

- **Filtrado de catálogo**: solo las herramientas relevantes para tu consulta se presentan al LLM, reduciendo drásticamente el número de tokens consumidos
- **Aprendizaje de patrones**: los planes validados se memorizan y reutilizan sin volver a llamar al LLM
- **Message Windowing**: cada componente ve únicamente el contexto estrictamente necesario
- **Cache de prompts**: aprovechamiento de la caché nativa de los proveedores para limitar los costes recurrentes

Estas optimizaciones combinadas permiten una reducción significativa del consumo de tokens en comparación con el modo ReAct.

---

## 6. Transparencia radical

### 6.1. Sin caja negra

Cuando un asistente cloud ejecuta una tarea, ves el resultado. Pero ¿cuántas llamadas a la IA? ¿Qué modelos? ¿Cuántos tokens? ¿Qué coste? ¿Por qué esa decisión? No lo sabes.

LIA toma la postura contraria — **todo es visible, todo es auditable**.

### 6.2. El panel de debug integrado

Directamente en la interfaz de chat, un panel de debug expone en tiempo real cada conversación con el detalle del análisis de intención (clasificación del mensaje y puntuación de confianza), del pipeline de ejecución (plan generado, llamadas a herramientas con entradas/salidas), del pipeline LLM (cada llamada IA con modelo, duración, tokens y coste), del contexto inyectado (recuerdos, documentos RAG, diarios) y del ciclo de vida completo de la solicitud.

### 6.3. Seguimiento de costes al céntimo

Cada mensaje muestra su coste en tokens y en euros. El usuario puede exportar su consumo. El administrador dispone de dashboards en tiempo real con indicadores por usuario y cuotas configurables.

No pagas una suscripción que oculta los costes reales. Ves exactamente lo que cuesta cada interacción y puedes optimizar: modelo económico para el enrutado, más potente para la respuesta.

### 6.4. La confianza por la evidencia

La transparencia no es un añadido técnico. Cambia la relación con tu asistente: **entiendes** sus decisiones, **controlas** tus costes, **detectas** los problemas. Confías porque puedes verificar — no porque te lo pidan.

---

## 7. Profundidad emocional

### 7.1. Más allá de la memoria factual

Los grandes asistentes recuerdan tus preferencias y datos personales. Es útil, pero es superficial. LIA va más allá con una comprensión **psicológica y emocional** estructurada.

Cada recuerdo tiene un peso emocional (-10 a +10), una puntuación de importancia, un matiz de uso y una categoría psicológica. No es una simple base de datos — es un perfil que comprende lo que te conmueve, lo que te motiva, lo que te duele.

### 7.2. El Psyche Engine: una personalidad viva

Es el diferenciador más profundo de LIA. ChatGPT, Gemini, Claude — todos tienen una personalidad fija. Cada mensaje es una página en blanco emocional. LIA es diferente.

El **Psyche Engine** le da a LIA un estado psicológico dinámico que evoluciona en cada intercambio:

- **14 estados de ánimo** que fluctúan con el tono de la conversación (sereno, curioso, melancólico, animado...)
- **22 emociones** que se activan y se atenúan en respuesta a tus palabras
- **Una relación** que se profundiza mensaje a mensaje
- **Rasgos de personalidad** (Big Five) heredados de la personalidad elegida
- **Motivaciones** que influyen en la proactividad del asistente

No hablas con una herramienta — interactúas con una entidad cuyo vocabulario se calienta cuando se emociona, cuyas frases se acortan bajo tensión, cuyo humor aflora cuando el intercambio es ligero. Y nunca lo dice — lo **muestra**.

### 7.3. Los diarios personales

LIA lleva sus propias reflexiones en **diarios personales**: auto-reflexión, observaciones sobre el usuario, ideas, aprendizajes. Estas notas, redactadas en primera persona y teñidas por la personalidad activa, influyen de forma orgánica en las respuestas futuras.

Es una forma de introspección artificial — el asistente que reflexiona sobre sus interacciones y desarrolla sus propias perspectivas. El usuario mantiene el control total: lectura, edición, eliminación.

### 7.4. La seguridad emocional

Cuando se activa un recuerdo con una alta carga emocional negativa, LIA cambia automáticamente a modo protector: nunca bromear, nunca minimizar, nunca banalizar. El asistente adapta su comportamiento a la realidad emocional de la persona — no un tratamiento uniforme para todos.

### 7.5. El conocimiento de sí mismo

LIA dispone de una base de conocimientos integrada sobre sus propias funcionalidades, lo que le permite responder preguntas sobre lo que sabe hacer, cómo funciona y cuáles son sus límites.

---

## 8. Fiabilidad en producción

### 8.1. El verdadero desafío de la IA agéntica

La gran mayoría de los proyectos de IA agéntica nunca llegan a producción. Costes descontrolados, comportamiento no determinista, ausencia de trazas de auditoría, coordinación deficiente entre agentes. LIA ha resuelto estos problemas — y funciona en producción 24/7 sobre una Raspberry Pi.

### 8.2. Una stack de observabilidad profesional

LIA incorpora una observabilidad de grado producción:

| Herramienta | Rol |
| --- | --- |
| **Prometheus** | Métricas de sistema y de negocio |
| **Grafana** | Dashboards de monitorización en tiempo real |
| **Tempo** | Trazas distribuidas de extremo a extremo |
| **Loki** | Agregación de logs estructurados |
| **Langfuse** | Tracing especializado de llamadas LLM |

Cada solicitud se traza de extremo a extremo, cada llamada LLM se mide, cada error se contextualiza. No es un monitoring añadido a posteriori — es una **decisión arquitectónica fundamental** documentada en los Architecture Decision Records del proyecto.

### 8.3. Un pipeline anti-alucinación

El sistema de respuesta dispone de un mecanismo anti-alucinación en tres capas: formateo de datos con límites explícitos, directivas que imponen el uso exclusivo de datos verificados, y gestión de casos límite. El LLM está obligado a sintetizar únicamente lo que proviene de los resultados reales de las herramientas.

### 8.4. Human-in-the-Loop en 6 niveles

LIA no rechaza las acciones sensibles — te las **presenta** con el nivel de detalle adecuado: aprobación de plan, clarificación, revisión de borrador, confirmación destructiva, confirmación de operaciones masivas, revisión de modificaciones. Cada aprobación alimenta el aprendizaje — el sistema se acelera con el tiempo.

---

## 9. Apertura radical

### 9.1. Cero lock-in

ChatGPT te ata a OpenAI. Gemini a Google. Copilot a Microsoft.

LIA te conecta a **8 proveedores de IA simultáneamente**: OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen y Ollama (modelos locales). Puedes combinarlos: OpenAI para la planificación, Anthropic para la respuesta, DeepSeek para las tareas en segundo plano — todo configurable desde la interfaz de administración, en un clic.

Si un proveedor cambia sus tarifas o degrada su servicio, cambias al instante. Sin dependencias, sin trampas.

### 9.2. Estándares abiertos

| Estándar | Uso en LIA |
| --- | --- |
| **MCP** (Model Context Protocol) | Conexión de herramientas externas por usuario |
| **agentskills.io** | Skills inyectables con progressive disclosure |
| **OAuth 2.1 + PKCE** | Autenticación para todos los conectores |
| **OpenTelemetry** | Observabilidad estandarizada |
| **AGPL-3.0** | Código fuente completo, auditable, modificable |

### 9.3. Extensibilidad

Cada usuario puede conectar sus propios servidores MCP, ampliando las capacidades de LIA mucho más allá de las herramientas integradas. Los Skills (estándar agentskills.io) permiten inyectar instrucciones expertas en lenguaje natural — con un generador de Skills integrado para crearlos fácilmente.

La arquitectura de LIA está diseñada para facilitar la adición de nuevos conectores, canales, agentes y proveedores de IA. El código está estructurado con abstracciones claras y guías de desarrollo dedicadas (agent creation guide, tool creation guide) que hacen que la extensión sea accesible para cualquier desarrollador.

### 9.4. Multi-canal

La interfaz web responsive se complementa con una integración nativa de Telegram (conversación, mensajes de voz transcritos, botones de aprobación inline, notificaciones proactivas) y notificaciones push Firebase. Tu memoria, tus diarios y tus preferencias te siguen de un canal a otro.

---

## 10. Visión

### 10.1. La inteligencia que crece contigo

La combinación de memoria psicológica + diarios introspectivos + aprendizaje bayesiano + Psyche Engine crea una forma de inteligencia emergente: con el paso de los meses, LIA desarrolla una comprensión cada vez más matizada de quién eres. No es inteligencia artificial general — es una inteligencia **práctica, relacional y emocional**, al servicio de una persona específica.

### 10.2. Lo que LIA no pretende ser

LIA no es un competidor de los gigantes del cloud y no pretende rivalizar con sus presupuestos de investigación. Como chatbot conversacional puro, los modelos utilizados a través de su interfaz nativa probablemente serán más fluidos. Pero LIA no es un chatbot — es un **sistema de orquestación inteligente** que utiliza esos modelos como componentes, bajo tu control total.

### 10.3. Por qué existe LIA

LIA existe porque al mundo le falta un asistente IA que sea **tuyo**. Verdaderamente tuyo. Sencillo de administrar en el día a día. Compartible con tus seres queridos, cada uno con su propia relación emocional. Alojado en tu servidor. Transparente en cada decisión y cada coste. Capaz de una profundidad emocional que los asistentes comerciales no ofrecen. Fiable en producción. Y abierto — abierto en proveedores, en estándares y en código.

**Your Life. Your AI. Your Rules.**
