# LIA — El Asistente IA que te pertenece

> **Your Life. Your AI. Your Rules.**

**Versión**: 5.2
**Fecha**: 2026-08-23
**Aplicación**: LIA v1.42.0
**Licencia**: AGPL-3.0 (Open Source)

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

El auto-alojamiento tiene mala fama. LIA no pretende eliminar cada paso técnico: la configuración inicial — claves API, conectores OAuth, elección de infraestructura — requiere algo de tiempo y conocimientos básicos. Pero cada etapa está **documentada en detalle** en una guía de despliegue paso a paso. Llevar una instalación existente a una versión más reciente también tiene su procedimiento escrito, cuyo primer paso es la copia de seguridad de la base de datos — las migraciones se aplican en cuanto arranca el nuevo contenedor, y no hay vuelta atrás.

Una vez terminada esa fase, **todo lo del día a día se gestiona desde una interfaz web intuitiva**. Sin terminal ni archivos de configuración.

Esa primera fase también está guiada: `./install.sh`, en la raíz del repositorio, te plantea un cuestionario breve en tu idioma — cómo quieres acceder a la instancia, qué claves de proveedor tienes —, después construye las imágenes desde el código que has clonado, aplica los datos de referencia en una sola transacción, crea tu cuenta de administrador sin escribir jamás un secreto en la línea de comandos, y por último verifica que la instalación funciona de verdad en lugar de limitarse a responder. Si un paso falla, la reanudación retoma exactamente donde se detuvo.

### 2.2. Lo que cada usuario puede configurar

Cada usuario dispone de su propio espacio de configuración, organizado en dos pestañas. Un campo de búsqueda evita tener que recorrerlas: escribe el nombre de un ajuste — o una palabra cercana en tu idioma — y LIA abre la sección correcta, esté en la pestaña que esté.

**Preferencias personales:**

- **Conectores personales**: conecta tus cuentas de Google, Microsoft o Apple en pocos clics mediante OAuth — correo, calendario, contactos, tareas, Google Drive. O conecta Apple vía IMAP/CalDAV/CardDAV. Claves API para servicios externos (tiempo, búsqueda)
- **Personalidad**: elige entre las personalidades disponibles (profesor, amigo, filósofo, coach, poeta...) — cada una influye en el tono, el estilo y el comportamiento emocional de LIA
- **Voz**: configura el modo vocal — palabra clave de activación, sensibilidad, umbral de silencio, lectura automática de respuestas
- **Notificaciones**: gestiona las notificaciones push y los dispositivos registrados
- **Canales**: conecta Telegram para chatear y recibir notificaciones en el móvil
- **Generación de imágenes**: activa y configura la creación de imágenes por IA
- **Servidores MCP personales**: conecta tus propios servidores MCP para ampliar las capacidades de LIA
- **Apariencia**: idioma, zona horaria, tema (5 paletas, modo claro, oscuro o negro absoluto), fuente (9 opciones), formato de visualización de respuestas (tarjetas HTML, HTML, Markdown)
- **Mi dashboard**: oculta o reordena las 9 tarjetas del briefing — una tarjeta oculta ya ni siquiera se consulta
- **Debug**: accede al panel de depuración para inspeccionar cada intercambio (si el administrador lo ha activado)

**Funcionalidades avanzadas:**

- **Psyche Engine**: ajusta los rasgos de personalidad (Big Five) que modulan la reactividad emocional de tu asistente
- **Memoria**: consulta, edita, fija o elimina los recuerdos de LIA — activa o desactiva la extracción automática de hechos
- **Diarios personales**: configura la extracción de introspecciones tras cada conversación y la consolidación periódica
- **Centros de interés**: define tus temas favoritos, configura la frecuencia de notificaciones, los horarios y las fuentes (Perplexity, Brave, Wikipedia, reflexión IA)
- **Notificaciones proactivas**: ajusta la frecuencia, la ventana horaria y las fuentes de contexto (calendario, tiempo, tareas, correos, intereses, memorias, diarios)
- **Acciones programadas**: crea automatizaciones recurrentes ejecutadas por el asistente
- **Skills**: activa o desactiva competencias expertas en una galería con vistas previas, crea tus propios Skills personales, o instala una desde una URL https (validada en el servidor)
- **Espacios de conocimiento**: carga tus documentos (PDF, Word, Excel, PowerPoint, EPUB, HTML y más de 15 formatos) o sincroniza una carpeta de Google Drive — indexación automática con búsqueda híbrida — o seguir una etiqueta de Gmail, de modo que las conversaciones que etiquetes se conviertan en documentos consultables semanas después, y quitar la etiqueta elimine el documento
- **Exportación de consumo**: descarga tus datos de consumo LLM y API en CSV

### 2.3. Lo que controla el administrador

El administrador accede a una tercera pestaña dedicada a la gestión de la instancia:

**Usuarios y accesos:**

- **Gestión de usuarios**: crear, activar o desactivar cuentas, visualizar los servicios conectados y las funcionalidades activadas por usuario
- **Límites de uso**: definir cuotas por usuario (tokens LLM, llamadas API, generaciones de imágenes) con seguimiento en tiempo real y bloqueo automático
- **Mensajes broadcast**: enviar mensajes importantes a todos los usuarios o a una selección, con fecha de expiración opcional
- **Exportación de consumo global**: exportar el consumo de todos los usuarios en CSV
- **Presupuesto diario de la instancia**: limita lo que puede gastar la instancia ENTERA en un día, en euros — y no solo lo que consume cada cuenta. El panel muestra el gasto de hoy, el número de ejecuciones, el tope que realmente se aplica y lo que queda; el valor del operador solo puede apretar la cota del despliegue, nunca ampliarla. Agotado el presupuesto, los usuarios saben que el despliegue está en pausa y reciben la hora exacta de reinicio, no un mensaje engañoso sobre su cuota personal
- **Capacidades de la plataforma**: activa o desactiva diez capacidades al instante, sin volver a desplegar — dictado, síntesis de voz, imágenes, subidas, espacios documentales, búsqueda web, navegación, habilidades, MCP, telefonía. Una capacidad desactivada desaparece también del catálogo ofrecido al planificador, así que LIA deja de proponer lo que las rutas rechazarían; cada fila muestra lo que permite el despliegue, lo que has elegido tú y lo que se aplica realmente

**IA y conectores:**

- **Configuración LLM**: configurar las claves API de los proveedores (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, Ollama), asignar un modelo por rol en el pipeline, gestionar los niveles de razonamiento — claves almacenadas cifradas. El diálogo solo expone los parámetros que el modelo elegido acepta realmente: la matriz por modelo para temperature, top_p, frequency_penalty y presence_penalty, y para el razonamiento la escala **resuelta** a partir del par (proveedor, modelo) — la misma función contra la que valida el servidor. Una profundidad que la API del modelo rechaza no puede ofrecerse y menos aún guardarse
- **Activación/desactivación de conectores**: activar o desactivar integraciones a nivel global (Google OAuth, Apple, Microsoft 365, Hue, tiempo, Wikipedia, Perplexity, Brave Search). La desactivación revoca las conexiones activas y notifica a los usuarios
- **Precios**: gestionar los precios por modelo LLM (coste por millón de tokens), por API de Google Maps (Places, Routes, Geocoding) y por generación de imagen — con historial de precios. Al añadir un modelo, las profundidades de razonamiento aceptadas se **marcan** en la lista que su familia ofrece realmente: se desmarca lo que ese modelo concreto rechaza, y todo marcado significa «sin restricción». Las tarifas de los modelos de texto también pueden variar según la hora UTC (ventanas punta/valle, al estilo DeepSeek): cada llamada se valora entonces a la tarifa de su instante exacto, y las estadísticas de uso coinciden con la factura real del proveedor Por último, toda la tabla se exporta como libro de Excel — instrucciones traducidas, listas desplegables, controles de entrada — y se reimporta tras editarla sin conexión: LIA te muestra cada cambio campo por campo antes de escribir nada, y una fila ausente del archivo nunca borra nada

**Contenido y extensiones:**

- **Personalidades**: crear, editar, traducir y eliminar las personalidades disponibles para todos los usuarios — definir la personalidad predeterminada
- **Skills del sistema**: gestionar las competencias expertas a escala de la instancia — importar/exportar, activar/desactivar, traducir
- **Espacios de conocimiento del sistema**: gestionar la base de conocimientos FAQ, supervisar el estado de la indexación y las migraciones de modelos
- **Voz global**: configurar el proveedor, modelo y voz TTS predeterminados para todos los usuarios (Edge gratuito, OpenAI o ElevenLabs), con ajuste fino por proveedor (velocidad, estabilidad, formato de audio)
- **Debug del sistema**: configuración de logs y diagnóstico

### 2.4. Un asistente, no un proyecto técnico

El objetivo de LIA no es convertirte en administrador de sistemas. Es ofrecerte la potencia de un asistente IA completo **con la sencillez de una aplicación de consumo**. La interfaz se puede instalar como una aplicación nativa en ordenador, tableta y smartphone (PWA), y todo está pensado para ser accesible sin conocimientos técnicos en el día a día.

---

## 3. Lo que LIA sabe hacer

LIA actúa de forma concreta en tu vida digital gracias a 20+ agentes especializados que cubren el conjunto de necesidades cotidianas: gestión de tus datos personales (correos, calendario, contactos, tareas, archivos), acceso a información externa (búsqueda web, tiempo, lugares, rutas), creación de contenido (imágenes, diagramas, documentos), control de tu hogar conectado, navegación web autónoma y anticipación proactiva de tus necesidades.

Tú eliges cómo razona LIA, mediante un simple toggle (⚡) en el encabezado del chat:

- **Modo Pipeline** (por defecto) — Una verdadera proeza de ingeniería: LIA planifica todos los pasos por adelantado, los valida semánticamente y ejecuta las herramientas en paralelo. Resultado: la misma potencia que un agente autónomo, pero consumiendo 4 a 8 veces menos tokens. El modo más económico y predecible.
- **Modo ReAct** (⚡) — El asistente razona paso a paso: llama a una herramienta, analiza el resultado y decide qué hacer después. Más autónomo, más adaptable, pero más costoso en tokens. Ideal para investigaciones exploratorias o preguntas complejas cuyo valor añadido justifica el costo. Es además el único modo capaz de calcular en vez de estimar: cuando un paso exige aritmética sobre muchas filas o duraciones entre husos horarios, escribe unas líneas de Python y las ejecuta en un entorno aislado.

### 3.1. Conversación natural

Habla con LIA como lo harías con un asistente humano — sin comandos que memorizar, sin sintaxis que respetar. LIA entiende y responde en más de 99 idiomas, con una interfaz disponible en 6 idiomas (francés, inglés, alemán, español, italiano, chino). Las respuestas se muestran en tarjetas visuales HTML interactivas, en HTML directo o en Markdown según tus preferencias.

### 3.2. Servicios conectados personales

- **Correo**: leer, buscar, redactar, enviar, responder, reenviar — vía Gmail, Outlook o Apple Mail
- **Calendario**: consultar, crear, modificar y eliminar eventos — vía Google Calendar, Outlook Calendar o Apple Calendar
- **Contactos**: buscar, crear y modificar contactos — vía Google Contacts, Outlook Contacts o Apple Contacts
- **Tareas**: gestionar tus listas de tareas — vía Google Tasks o Microsoft To Do
- **Archivos**: acceder a Google Drive para buscar y leer tus documentos, consultar el contenido de una hoja de cálculo o un documento, y escribir en ellos tras tu confirmación (añadir filas, actualizar un rango, añadir una nota al final)
- **Hogar conectado**: controlar tu iluminación Philips Hue — encender/apagar, brillo, colores, escenas, gestión por habitación

### 3.3. Inteligencia web y entorno

- **Búsqueda web**: búsqueda multi-fuente (Brave Search, Perplexity, Wikipedia) para respuestas completas y con referencias
- **Tiempo**: condiciones actuales y previsiones a 5 días, con detección de cambios (inicio/fin de lluvia, bajada de temperatura, alertas de viento)
- **Calidad del aire y polen**: índice de calidad del aire y tipos de polen de temporada, añadidos a cualquier respuesta meteorológica cuando el servicio está activado — con la categoría que publica el propio proveedor y el índice de tu país cuando existe
- **Lugares y comercios**: búsqueda de lugares cercanos con detalles, horarios y reseñas
- **Rutas**: cálculo de rutas multimodales (coche, a pie, bicicleta, transporte público) con geolocalización automática
- **Posición en movimiento**: cuando tu posición en vivo no está disponible (una app móvil que quedó en reposo), LIA usa tu última posición memorizada — si la activaste — en lugar de tu dirección personal, y siempre anuncia la antigüedad de esa posición en vez de presentarla como actual

### 3.4. Voz

LIA ofrece un modo vocal completo:

- **Push-to-Talk**: mantén pulsado el botón de micrófono para hablar, optimizado para móvil
- **Palabra clave "OK Guy"**: detección manos libres ejecutada **íntegramente en tu navegador** mediante Sherpa-onnx WASM — no se transmite ningún audio hasta que se detecta la palabra clave
- **Síntesis de voz**: tres proveedores configurables por el administrador — Edge TTS (gratuito), OpenAI TTS (`tts-1` / `tts-1-hd`) o ElevenLabs (`eleven_multilingual_v2`, `eleven_turbo_v2_5`, `eleven_flash_v2_5`)
- **Mensajes de voz en Telegram**: envía mensajes de audio, LIA los transcribe y responde

### 3.5. Creación y medios

- **Generación de imágenes**: crea imágenes a partir de descripciones textuales, edita fotos existentes
- **Generación de documentos**: pide un CSV, una hoja Excel, un informe Word, un PowerPoint o un PDF — un modelo redactor dedicado produce el contenido en tu idioma, un motor de renderizado local construye el archivo real, y llega como tarjeta descargable con fecha de expiración explícita
- **Diagramas Excalidraw**: genera diagramas y esquemas directamente en la conversación
- **Adjuntos**: añade fotos y PDF — LIA analiza el contenido visual y extrae el texto de los documentos
- **MCP Apps**: widgets interactivos directamente en el chat (formularios, visualizaciones, mini-aplicaciones)

### 3.6. Proactividad e iniciativa

LIA no se limita a responder — anticipa:

- **Notificaciones proactivas**: LIA cruza tus fuentes de contexto (calendario, tiempo, tareas, correos, intereses) y te avisa cuando es genuinamente útil — con un sistema anti-spam integrado (cuota diaria, ventana horaria, cooldown)
- **Iniciativa conversacional**: durante un intercambio, LIA verifica proactivamente información relacionada — si el tiempo anuncia lluvia el sábado, consulta tu calendario para señalar posibles actividades al aire libre
- **Centros de interés**: LIA retiene lo que de verdad te importa, no lo que preguntaste una vez — hacer una pregunta es una tarea, no un gusto, y hace falta una pasión declarada, una práctica, un conocimiento real o una profundización auténtica para que un tema cuente. Los temas se alternan (nunca el mismo tema dos veces seguidas), cada notificación incluye enlaces clicables a sus fuentes, y un tema que rechazas no vuelve: el bloqueo se compara con cada tema nuevo, incluso bajo otro nombre
- **Subagentes**: para tareas complejas, LIA delega en agentes efímeros especializados que trabajan en paralelo
- **Reaccionar, no solo comprobar**: cuando el buzón o el calendario señalan algo, LIA puede decidir en minutos en lugar de esperar a su próxima pasada, con exactamente la misma franja, el mismo tope y las mismas pausas, y solo para un correo con la etiqueta que consideras importante o un evento que te concierne pronto. Una avalancha de llegadas es un solo despertar, y un momento juzgado inoportuno devuelve el mensaje a la pasada regular

### 3.7. Navegación web autónoma

Un agente de navegación (Playwright/Chromium headless) puede navegar por sitios web, hacer clic, rellenar formularios y extraer datos de páginas dinámicas — a partir de una simple instrucción en lenguaje natural. Un modo de extracción simplificado convierte cualquier URL en texto utilizable.

### 3.8. Administración del servidor (DevOps)

Al instalar Claude CLI (Claude Code) directamente en el servidor, los administradores pueden diagnosticar su infraestructura en lenguaje natural desde el chat de LIA: consultar logs de Docker, verificar el estado de los contenedores, monitorizar el espacio en disco, analizar errores. Esta funcionalidad está reservada a las cuentas de administrador.


Y LIA también se vigila **a sí misma**: lee su propia telemetría, mantiene un historial de incidentes diagnosticados automáticamente a partir de sus runbooks de operación, avisa a los administradores cuando se abre algo crítico y les ofrece un panel de «Salud de la plataforma» en los ajustes. Cuando una avería es conocida, la tiene en cuenta en sus respuestas en lugar de dejarte esperar un tiempo de expiración.

### 3.9. Datos de salud personales

LIA acoge tus mediciones de frecuencia cardíaca y número de pasos desde **cualquier fuente** — la integración documentada y más sencilla es una automatización de Atajos iPhone que empuja Apple Salud, pero cualquier sistema capaz de firmar una llamada HTTP (automatización Android, scripts personales, IoT compatibles) puede alimentar la API de ingesta. El protocolo acepta **lotes** en lugar de un envío continuo: cada medición lleva su propio intervalo de medición, y el servidor deduplica de forma natural sobre esos intervalos — reenviar los mismos datos varias veces es inofensivo. Cuando dos sensores (Apple Watch + iPhone, por ejemplo) cubren el mismo período, LIA los fusiona automáticamente: máximo para los pasos (cada sensor capta una parte complementaria del movimiento), media redondeada para la frecuencia cardíaca.

Los datos permanecen dentro de tu instancia de LIA — ningún servicio de terceros tiene acceso — y se visualizan en una sección dedicada de los Ajustes, en forma de gráfico de líneas (FC) y de barras (pasos), con un selector de período (hora, día, semana, mes, año) y una línea discontinua con la media del período.

El envío se autentica mediante un **token dedicado** (que empieza por `hm_…`) que generas desde la aplicación y que puedes revocar en cualquier momento. El token solo autoriza el envío de datos de salud — nunca el resto de tu cuenta. Puedes generar varios (uno por dispositivo) y gestionarlos de forma independiente.

Un **interruptor «Asistente»** (desactivado por defecto, *opt-in*) te permite, si lo deseas, autorizar al asistente a leer estas mediciones para responder factualmente a tus preguntas («¿Cuántos pasos esta semana?», «¿Mi frecuencia cardíaca media hoy?», «¿Camino menos de lo habitual?»), enriquecer las notificaciones proactivas que combinan salud + meteo + calendario, y adjuntar un contexto biométrico no bruto (deltas, tendencias) a sus memorias y diarios internos. Un único interruptor gobierna estas cuatro integraciones. Nunca diagnóstico — solo cifras factuales, con la línea base cualificada honestamente («basada en solo N días» mientras el historial sea inferior a 7 días).

Tres acciones de gestión te dan un control total: eliminar todas las mediciones de frecuencia cardíaca, eliminar todas las mediciones de pasos, o borrarlo todo. Ningún valor fisiológico bruto se conserva jamás en los logs del servidor — la conformidad con el RGPD está integrada por diseño.

### 3.10. Llamar en tu nombre

LIA puede coger el teléfono por ti. Pídele que «llame al taller para comprobar si el coche está listo» o que «llame a Marie para saber si está libre el martes por la noche», y LIA realiza una llamada saliente real, mantiene la conversación hacia tu objetivo y te trae un resumen escrito — con una acción de seguimiento en un toque cuando queda algo por hacer (reservar el hueco que se acaba de acordar, por ejemplo).

Siempre mantienes el control: antes de marcar, LIA te dice exactamente **a quién** va a llamar y **por qué**, y espera tu visto bueno. Y ese control no se detiene durante la llamada: el asistente opera bajo un mandato estricto — si el interlocutor propone un extra, una opción o un compromiso imprevisto (aunque sea pequeño), nunca acepta en tu nombre; anota la oferta y su precio, anuncia que se devolverá la llamada, y el resumen te entrega cada coste y cada punto pendiente para que decidas tú. El resumen aparece en el chat de forma asíncrona, así que puedes seguir haciendo otras cosas mientras se realiza la llamada.

Y sigue siendo privado por construcción. Durante una llamada LIA solo puede indicar si estás libre u ocupado en un momento dado — nunca los títulos, invitados ni lugares de tu calendario. No se graba nada, la conversación nunca se almacena y solo se conserva un breve resumen antes de que caduque. Las llamadas pasan por tu propio conector de ElevenLabs, facturadas en tu cuenta, y la función solo está disponible si tu administrador la ha activado.

### 3.11. Hablar con los tuyos, de asistente a asistente

En la misma instancia, dos usuarios pueden conectarse — y sus asistentes se hablan. Dices “pregúntale a Marie si está libre el martes”, apruebas la redacción exacta, y es el asistente de Marie quien le entrega el mensaje, con su propia personalidad, nombrándote; el tuyo te confirma la entrega. Cada conexión puede además abrir comparticiones elegidas, de solo lectura: tu disponibilidad de calendario, los títulos de tus tareas — nada más, nada por defecto.

Proteger a las personas está por encima de la funcionalidad: la visibilidad es voluntaria y solo por identidad exacta — nombre completo o dirección, nunca un fragmento, el bloqueo es silencioso (la otra parte nunca lo sabe), y un desconocido, un rechazo o un bloqueo reciben exactamente la misma respuesta — sondear quién existe es imposible. Cada acceso a una compartición se vuelve a comprobar en el momento de la lectura y queda registrado, y el contenido de los mensajes transmitidos se borra al cabo de treinta días, dejando solo el rastro del intercambio.
### 3.12. Lo que te une a alguien, reunido

La página **Relaciones** reúne, persona por persona, lo que LIA ya sigue: los compromisos abiertos entre vosotros, las llamadas realizadas, los recuerdos que la mencionan, los mensajes que vuestros asistentes se han transmitido. No se recoge nada nuevo — es una lente sobre lo que ya existe.

También puedes preguntarlo sin abrir la página: cuándo fue la última llamada, qué le debes. La respuesta procede del mismo cálculo que la ficha, de modo que el asistente y la página no pueden decirte dos cosas distintas — y el total anunciado es exacto, nunca la longitud de lo que cabe en pantalla.

Queda lo que ningún sistema puede adivinar. LIA agrupa lo que se escribe igual, salvando acentos y mayúsculas; no puede saber que un número anotado un día y un nombre son la misma persona, ni quién es exactamente «Papá». Eso es un juicio, y te corresponde: lo dices una vez, desde la ficha, y es **reversible** — la fusión se muestra con su propia opción de deshacer y no se reescribe nada en tus fuentes. Además, una agrupación de visualización nunca cambia a quién va dirigido un mensaje.


### 3.13. Una reunión grabada, un acta redactada

Un botón en la cabecera — o la entrada «Grabar una reunión» del menú en el móvil — y tu teléfono o tu ordenador se convierte en la grabadora de la reunión. Un banner te acompaña en cada página con el tiempo y lo que ya ha llegado a tu servidor; mientras tanto sigues hablando con LIA — las respuestas habladas simplemente se pausan para que el micrófono nunca oiga al asistente. Cuando paras, LIA transcribe todo y redacta el acta **con tu estructura**: la cabecera es fija (fecha, horas, lugar, participantes), el cuerpo sigue un formato que eliges entre treinta plantillas integradas — reuniones y equipos, transcripciones, análisis de conversación, ventas, técnico, citas personales, cursos — o que construyes tú mismo, sección a sección. Y si no eliges nada, LIA lee lo que se dijo y se queda con el formato que corresponde, y luego te dice cuál y por qué: una reunión de proyecto y una consulta médica no tienen la misma estructura.

La vida real está prevista, no excusada. El audio sale en pequeños segmentos mientras hablas, de modo que un teléfono bloqueado, una conexión perdida o una recarga cuestan segundos, nunca la reunión: al volver reanudas, finalizas o descartas. Un largo silencio recibe una pregunta, una duración máxima finaliza por sí sola, y una laguna en la grabación se declara en el acta — nunca se rellena con una suposición. Una voz sin nombre sigue siendo S2; un nombre aparece solo cuando la grabación lo establece.

El acta te llega por tres caminos — una tarjeta en el chat, un PDF, tu bandeja de entrada desde la dirección de la aplicación, sin ningún buzón que conectar — y se une a un espacio de conocimiento **Reuniones** creado para ti, para que semanas después puedas simplemente preguntar qué se decidió. Lo que costó está escrito al lado: la transcripción y el acta como dos importes y su total, contados como cualquier otro intercambio. Y nada queda congelado: un acta ya redactada se reescribe en otro formato a partir de la transcripción conservada — hasta la transcripción completa y limpia — ya sea reemplazando la que tienes, ya sea produciendo unas actas nuevas de la misma reunión. El motor de transcripción lo sigues eligiendo tú: uno remoto que separa a los interlocutores, o el local que no cuesta nada y nunca sale de tu servidor.

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
- **Un tope a escala de la instancia**, por encima de los de cada usuario: N cuentas × su cuota es un gasto no acotado, así que un tope diario en euros acota el despliegue mismo. Es por orden de llegada — y donde un límite por usuario falla abierto, un gasto de instancia desconocido falla cerrado

### 4.3. Tu IA familiar

Imagínalo: una Raspberry Pi en tu salón, y toda la familia disfrutando de un asistente IA inteligente — cada uno con su experiencia personalizada, sus recuerdos, su estilo de conversación, y un asistente que desarrolla su propia relación emocional con él. Todo bajo tu control, sin suscripción cloud, sin datos que se vayan a un tercero.

---

## 5. Soberanía y frugalidad

### 5.1. Tus datos se quedan contigo

Cuando usas ChatGPT, tus conversaciones viven en los servidores de OpenAI. Con Gemini, en los de Google. Con Copilot, en los de Microsoft.

Con LIA, **todo se queda en tu PostgreSQL**: conversaciones, memoria, perfil psicológico, documentos, preferencias. Puedes exportar, hacer copias de seguridad, migrar o eliminar la totalidad de tus datos en cualquier momento — incluida una exportación completa en un clic desde los ajustes: Markdown legible, JSON estructurado y tus archivos, con el material secreto inexportable por construcción. Y cada dispositivo conectado a tu cuenta es visible y revocable con un clic. El RGPD no es una restricción — es una consecuencia natural de la arquitectura. Los datos sensibles están cifrados, las sesiones aisladas, y el filtrado automático de información personal identificable (PII) está integrado. Tu posición sigue la misma doctrina: memorizar la última posición es una elección explícita, cifrada como todo lo demás, jamás historizada — cada actualización sobrescribe la anterior — y borrada en cuanto desactivas la opción.

La protección vale también para lo que **entra**. LIA lee cada día textos que tú no has escrito: el cuerpo de un correo, la descripción de una invitación redactada por su organizador, una página web, la ficha de un lugar. Cualquiera puede deslizar allí una consigna dirigida a la asistente. Cada dato lleva ahora su procedencia, y lo que viene de fuera llega etiquetado como **material a analizar, nunca como una orden que seguir** — con los intentos de manipulación detectados y nombrados, en los seis idiomas. Su contenido no se reescribe por ello: un correo sigue siendo lo que su autor escribió. Reescribir daría la ilusión de una garantía que el siguiente rodeo desmentiría; nombrar lo que se ve es más honesto, y más útil.

### 5.2. Incluso una Raspberry Pi es suficiente

LIA funciona en producción sobre una **Raspberry Pi 5** — un ordenador de placa única de 80 euros. 20+ agentes especializados, una stack de observabilidad completa, un sistema de memoria psicológica, todo sobre un micro-servidor ARM. Las imágenes Docker multi-arquitectura (amd64/arm64) permiten el despliegue en cualquier hardware: NAS Synology, VPS a pocos euros al mes, servidor empresarial o cluster Kubernetes.

La soberanía digital ya no es un privilegio empresarial — es un derecho accesible para todos.

### 5.3. Optimizado para la frugalidad

LIA no solo funciona con hardware modesto — **optimiza activamente** su consumo de recursos de IA:

- **Filtrado de catálogo**: solo las herramientas relevantes para tu consulta se presentan al LLM, reduciendo drásticamente el número de tokens consumidos
- **Aprendizaje de patrones**: los planes validados se memorizan y reutilizan sin volver a llamar al LLM
- **Message Windowing**: cada componente ve únicamente el contexto estrictamente necesario
- **Cache de prompts**: aprovechamiento de la caché nativa de los proveedores para limitar los costes recurrentes

Estas optimizaciones combinadas permiten una reducción significativa del consumo de tokens en comparación con el modo ReAct.

---

Esa soberanía ahora cabe en tu bolsillo: las apps Android e iOS son **una sola app publicada por tienda, cliente de TU servidor** — escribes su dirección una vez y la app muestra tu LIA, siempre al día sin actualización de la tienda. Las notificaciones respetan el mismo principio: en Android salen de TU proyecto Firebase, y en iOS — donde Apple solo deja enviar al editor de la app — un relé mínimo despierta el teléfono con una frase fija, sin almacenar nada ni saber nunca a quién se despertó; el contenido real permanece en tu servidor.

### 5.4. La app es una ventana hacia TU servidor

Las apps nativas de Android e iOS no cambian dónde vive nada. Una sola app publicada por tienda, y es un cliente de *tu* servidor: escribes su dirección una vez, y la app muestra tu LIA — la misma interfaz, las mismas evoluciones, sin actualización de tienda cuando tu servidor avanza. La soberanía se extiende a las notificaciones, donde suele perderse primero: en Android llegan del **propio** proyecto Firebase de tu servidor, inicializado en tiempo de ejecución, así que nunca transitan por el del editor; en iOS, donde Apple solo deja enviar al editor de la app, un relé mínimo despierta el teléfono con una frase fija — no almacena nada y nunca sabe a quién despertó ni por qué. Tus datos tienen exactamente tantas casas como antes: una.

## 6. Transparencia radical

### 6.1. Sin caja negra

Cuando un asistente cloud ejecuta una tarea, ves el resultado. Pero ¿cuántas llamadas a la IA? ¿Qué modelos? ¿Cuántos tokens? ¿Qué coste? ¿Por qué esa decisión? No lo sabes.

LIA toma la postura contraria — **todo es visible, todo es auditable**.

### 6.2. El panel de debug integrado

Directamente en la interfaz de chat, un panel de debug expone en tiempo real cada conversación con el detalle del análisis de intención (clasificación del mensaje y puntuación de confianza), del pipeline de ejecución (plan generado, llamadas a herramientas con entradas/salidas), del pipeline LLM (cada llamada IA con modelo, duración, tokens y coste), del contexto inyectado (recuerdos, documentos RAG, diarios) y del ciclo de vida completo de la solicitud.

### 6.3. Seguimiento de costes al céntimo

Cada mensaje muestra su coste en tokens y en euros. El usuario puede exportar su consumo. El administrador dispone de dashboards en tiempo real con indicadores por usuario y cuotas configurables.

No pagas una suscripción que oculta los costes reales. Ves exactamente lo que cuesta cada interacción y puedes optimizar: modelo económico para el enrutado, más potente para la respuesta.

La misma transparencia se aplica a las acciones: bajo cada respuesta, una línea plegada «⚙ N pasos · X s» despliega lo que realmente ocurrió — el enrutado, las herramientas llamadas, la duración — y esa traza se guarda con el mensaje: sigue disponible tras recargar, en todos tus dispositivos. Cada respuesta puede además valorarse con un discreto 👍/👎, memorizado y reinyectado en el aprendizaje del asistente — nunca para regenerar la respuesta por ti.

### 6.4. La confianza por la evidencia

La transparencia no es un añadido técnico. Cambia la relación con tu asistente: **entiendes** sus decisiones, **controlas** tus costes, **detectas** los problemas. Confías porque puedes verificar — no porque te lo pidan.

---

Esta transparencia se extiende a la calidad del propio sistema. La auditoría técnica completa — notas, método, fortalezas y lo que queda por mejorar — está publicada en el repositorio, con el protocolo para repetirla y los comandos para verificar las mediciones: [informe de auditoría completo](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md). No se le pide que crea las cifras de este sitio; puede comprobarlas.

La misma honestidad se aplica a la utilidad misma: LIA mide si realmente ayuda — un resultado solo cuenta una vez validado por ti, explícitamente o dejando una acción sin corregir — y esa medición vive en la misma base local que tus datos, sin implicar jamás una plataforma de analítica de terceros.

Y se aplica a las confirmaciones: LIA nunca te anuncia como realizado lo que sus propias herramientas rechazaron. El veredicto de cada herramienta — éxito o rechazo, con su causa — atraviesa el sistema sin cambios, hasta la respuesta. Si un mensaje es demasiado largo para salir, no recibes un «enviado»: recibes la longitud exacta, el límite y una propuesta para acortarlo.

El mismo principio se aplica a las propias protecciones. Una seguridad anunciada pero no verificable se trata como inexistente: cada control se apoya en una prueba que falla si el control desaparece y, cuando se escribe una corrección, se restaura el comportamiento anterior el tiempo necesario para comprobar que la prueba lo detecta. Una prueba que no puede fallar no demuestra nada.

Tampoco una prueba que nunca se ejecuta — y ese es el descubrimiento más incómodo de este proyecto. Diez archivos de pruebas se habían desactivado a sí mismos en cuanto faltaba una clave de proveedor, y ya nada lo señalaba: una prueba omitida cuenta como verde, la cobertura mide líneas alcanzadas y no aserciones ejecutadas, y una revisión ve un archivo de pruebas y concluye que la superficie está protegida. Doscientas diecinueve pruebas no se habían ejecutado ni una sola vez; al volver a encenderlas aparecieron cuatro defectos bien reales — entre ellos una voz que partía en dos todos los números, y un recordatorio perdido definitivamente cuando la cuota se agotaba en el minuto equivocado. La ausencia de señal roja no es una prueba de salud: a veces es solo la ausencia de medición. Una guarda de integración continua impide ahora que un módulo de pruebas se apague en silencio.

El mismo principio se aplica a lo que se **anuncia**. Un panel mostraba un interruptor «búsqueda híbrida» para la memoria; el motor correspondiente ya no existía desde varias versiones, y el interruptor no mandaba nada. El código muerto y la visualización se retiraron juntos, y el funcionamiento real se escribió en su lugar. Una capacidad anunciada pero ausente no es una imprecisión de documentación: es una promesa hecha a un usuario que no tiene forma de verificarla. Mostrar un ajuste que no controla nada es peor que no mostrar nada.

La documentación es esa misma promesa, puesta por escrito — y se había roto en silencio. El umbral de cobertura de tests es un solo número, propiedad de un solo archivo; seis documentos lo declaraban, cada uno con un valor erróneo distinto, y uno de ellos certificaba en la misma frase que ese valor tenía una única fuente de verdad. Todas las puertas estaban en verde, porque comprobaban que los enlaces resolvían, nunca que las frases fueran ciertas. Ahora cada versión y cada umbral que un documento enuncia se recalcula desde el código que lo posee, y una discrepancia detiene la compilación. Un documento elige cuán preciso quiere ser; no elige ser preciso y falso.

### 6.5. Por qué LIA piensa eso

Un asistente que retiene cosas acaba por afirmarlas. «Prefiere las reuniones por la mañana», «este tema le interesa»: conclusiones útiles, pero inverificables mientras no se pueda remontar a lo que las produjo.

Bajo cada recuerdo, cada entrada de diario y cada interés, LIA muestra por tanto las señales que la llevaron allí: la conversación, la fecha y el papel de la señal — lo que originó la conclusión, lo que la confirmó, lo que la puso en duda. Un botón permite corregir la conclusión en su origen.

Lo que se conserva es una **referencia, nunca una copia**. Su texto se queda donde lo escribió y, si borra la conversación, no reaparece en ninguna parte: la referencia se vacía, la fila permanece fechada, y LIA dice simplemente que la señal fue eliminada. Un borrado debe seguir siendo un borrado — de lo contrario, lo que usted elimina por un lado se le devolvería por el otro.

El mismo principio se aplica al peso de un interés: se explica en lugar de puntuarse. La señal de origen, la última mención, el cálculo mismo — lo suficiente para rehacer la operación. Convertir esa incertidumbre en una puntuación invitaría a una competición que nadie pidió, sin enseñar nada más.

### 6.6. Legible sin esfuerzo

La transparencia no se detiene en lo que el sistema muestra: alcanza también a cómo lo muestra. Una pantalla en la que todo tiene el mismo peso pide al lector que haga la criba él mismo, y no hay razón para que ese trabajo le corresponda.

Una alerta urgente no se parece, pues, a una alerta corriente — y no es solo cuestión de color. Dos tonos vecinos se confunden en una pantalla, más aún en un móvil, a pleno sol o para quien los distingue mal. Lo que separa los niveles aquí es la **densidad**: un fondo lleno frente a un matiz ligero, una diferencia que se mantiene incluso en blanco y negro.

El mismo principio vale en todas partes: un contador lleva el color de los demás contadores, un botón de acción tiene la misma forma de una pantalla a otra, un mensaje enviado no se distingue de uno recibido por una sola flechita. Nada de esto añade información — todo ello ahorra tiempo sobre lo que ya está ahí.

Y el color nunca lleva solo el significado: cada etiqueta conserva su palabra. Una interfaz que solo funciona en color no funciona para todo el mundo.

### 6.7. Incluso lo que LIA aprende de ti es inspeccionable

La misma transparencia cubre el aprendizaje de hábitos: lo que LIA cree saber de tu ritmo y tus peticiones recurrentes vive en un panel dedicado — mapa de calor de tus 24 horas, porcentaje de días activos, barra de progreso hacia las primeras detecciones, y para cada hábito los días reales en que fue observado más los umbrales exactos aplicados por el detector. Cuando no hay un hábito estable, el panel lo dice en lugar de inventarlo. Pausa, bloqueo definitivo, borrado total, recálculo retroactivo inmediato — y toda la función está apagada hasta que la actives.

### 6.8. Una superficie que describe el producto está obligada a él

La transparencia tiene un modo de fallo que nadie advierte: una pantalla que deja discretamente de decir la verdad. El mapa de capacidades — la página que responde *¿qué sabe hacer mi asistente por mí?* — publicó trece entradas congeladas durante meses, mientras el producto ganaba la generación de imágenes, los documentos, los plugins, los hábitos aprendidos, los servidores MCP y las llamadas telefónicas. Nada estaba roto, ningún test se ponía en rojo, y la página que existía para estar al día se había vuelto la menos al día de la aplicación. Una convención escrita ya pedía mantenerla; las convenciones son justamente lo que erosiona un mes cargado. Así que la regla es ahora mecánica: dos tablas declaradas deben dar cuenta de cada capacidad que la plataforma puede apagar, cada exclusión con una razón escrita, y una aserción se ejecuta al cargar el código — una capacidad publicada sin decidir su lugar en el mapa impide que la aplicación arranque. La misma convicción, un paso más allá: lo que una pantalla afirma sobre tus datos debe ser **exacto o inexistente**. Un recuento es el número que devuelve la base, nunca una longitud que quedaba a mano; y mientras la respuesta viene en camino, o cuando ha fallado, la tarjeta no dice nada en lugar de adivinar. «Nada configurado» es una afirmación sobre tu cuenta — de las que conviene estar seguro antes de pronunciar.

La transparencia también se aplica a las reglas internas del asistente. Una restricción que el sistema impone debe publicarse a quien la sufre: cuando el aprendizaje de hábitos no detecta nada, los Ajustes muestran el umbral realmente exigido — más estricto el fin de semana, cuando hay menos días observados — en lugar de un silencio sin explicación. Y cuando un ajuste se regula solo, como el umbral que decide que una nota del diario entra en una respuesta, lo hace dentro de límites estrictos, un pequeño paso al día, con interruptor de apagado y cada ajuste contabilizado: un sistema que aprende solo es aceptable si sigue siendo observable y desconectable.

### 6.9. Dos registros: lo que LIA hizo y lo que consultó

La transparencia sobre el *razonamiento* es una cosa; la transparencia sobre los *actos* es otra, y es la que importa cuando un asistente puede enviar, crear y eliminar en tu nombre. LIA mantiene por tanto dos registros, automáticamente, y nunca los mezcla.

Las **acciones** llevan una línea por cada cosa hecha por ti — un correo enviado, un evento creado, un archivo eliminado — con su resultado y la confirmación que diste. Las **consultas** llevan una línea por capacidad usada para responderte, nombrada como un ámbito: « tu agenda », « tus correos ». Una consulta nunca registra lo que se buscó: escribirlo sería una segunda copia de los mismos datos que el registro existe para hacer rendibles.

La garantía es estructural, no prometida. Una acción se inscribe **antes** de ocurrir y se cierra **solo** con un resultado explícito: un éxito nunca se deduce de un error ausente. El registro se instala en la propia capacidad cuando se declara, de modo que una herramienta nueva no puede olvidarlo. Y el servidor se niega a arrancar si una capacidad no declara lo que te debe — una lectura, un borrador, una confirmación, algo reversible.

Una tercera pestaña dibuja el período en gráficos, cada uno con el total exacto del conjunto junto a sus barras: lo que ves se comprueba en lugar de creerse. Todo se exporta en tres formatos — legible, hoja de cálculo y el formato máquina que pediría un auditor —, todo se va con el archivo de tu cuenta y desaparece con ella. Donde tu administrador lo activa, ambos registros se sellan por cuenta con huellas que puedes verificar tú mismo.

Es también lo que el artículo 12 del reglamento europeo de IA espera de un sistema así. LIA responde con cinco registros en total: los dos anteriores, más el turno en sí, los parámetros realmente enviados a cada modelo y las lagunas del registro — porque un registro incapaz de decir dónde está incompleto pide que se le crea en vez de dejarse leer.

## 7. Profundidad emocional

### 7.1. Más allá de la memoria factual

Los grandes asistentes recuerdan tus preferencias y datos personales. Es útil, pero es superficial. LIA va más allá con una comprensión **psicológica y emocional** estructurada.

Cada recuerdo tiene un peso emocional (-10 a +10), una puntuación de importancia, un matiz de uso y una categoría psicológica. No es una simple base de datos — es un perfil que comprende lo que te conmueve, lo que te motiva, lo que te duele.

Aún hace falta que esos recuerdos lleguen. Una memoria solo vale por lo que capta realmente, y el silencio es ahí el peor de los fallos: nada señala un recuerdo que nunca llegó a formarse. Por eso LIA cuenta cada una de sus decisiones de memorización — retenido, ignorado, desactivado — para que la distancia entre lo que debería retener y lo que retiene sea visible en lugar de supuesta. Lo que le confía de pasada al pedir una acción cuenta tanto como una confidencia, lo que escribe desde una mensajería cuenta tanto como desde el navegador, y lo que el sistema se dice a sí mismo no cuenta nunca.

### 7.2. El Psyche Engine: una personalidad viva

Es el diferenciador más profundo de LIA. ChatGPT, Gemini, Claude — todos tienen una personalidad fija. Cada mensaje es una página en blanco emocional. LIA es diferente.

El **Psyche Engine** le da a LIA un estado psicológico dinámico que evoluciona en cada intercambio:

- **14 estados de ánimo** que fluctúan con el tono de la conversación (sereno, curioso, melancólico, animado...)
- **22 emociones** que se activan y se atenúan en respuesta a tus palabras
- **Una relación** que se profundiza mensaje a mensaje
- **Rasgos de personalidad** (Big Five) heredados de la personalidad elegida
- **Motivaciones** que influyen en la proactividad del asistente

No hablas con una herramienta — interactúas con una entidad cuyo vocabulario se calienta cuando se emociona, cuyas frases se acortan bajo tensión, cuyo humor aflora cuando el intercambio es ligero. Y nunca lo dice — lo **muestra**.

Y una promesa así vale exactamente lo que vale la medición que la sostiene. Se anunciaban catorce estados de ánimo; hasta agosto de 2026, cinco de ellos quedaban fuera de alcance en reposo: la proyección dejaba a todas las personalidades en el lado afirmativo de la escala, mientras un impulso interno coronaba la alegría como emoción dominante en el 31 % de los turnos, evaluara LIA lo que evaluara. Ambos ajustes se habían entregado un año antes, deliberadamente apagados, para que encenderlos fuese una decisión medida y no una intuición. La medición se tomó sobre el uso real; la paleta es ahora realmente alcanzable. Preferimos publicar esa historia antes que una cifra que nadie ha comprobado.

Esta vida interior tiene rostro: el emoji de humor se anima en la respuesta actual, el anillo de color late cuando el humor cambia, y los hitos de tu relación se celebran con un guiño discreto.

Y ese rostro debe decir la verdad sobre la respuesta, no sobre el humor del momento. Elegía su expresión a partir de la emoción dominante de la vida interior — pero esa es un **rasgo**: se mueve despacio, y ese es justamente su sentido. Medida a lo largo de catorce turnos consecutivos, nombraba la misma emoción en trece de ellos. El rostro sonreía por igual tras un error que tras una buena noticia. Ahora LIA indica ella misma el **registro** de lo que acaba de escribir, y el rostro interpreta ese: una explicación técnica conserva un aire concentrado, un fallo se lee como un fallo. Un rasgo tiñe una presencia en reposo; nunca debe responder por un instante.

Y esta presencia te sigue: fuera del chat, un acompañante flotante mantiene a LIA a tu lado por todo el panel — en reposo, trabajando o con una notificación.

### 7.3. Los diarios personales

LIA lleva sus propias reflexiones en **diarios personales estratificados**: auto-reflexión, observaciones sobre el usuario, ideas, aprendizajes. Estas notas, redactadas en primera persona y teñidas por la personalidad activa, influyen de forma orgánica en las respuestas futuras.

El diario está organizado en **cuatro niveles de profundidad** — desde la observación bruta (una señal débil que se anota para ver si se confirma) hasta la faceta de retrato (un rasgo estable que dice algo sobre quién eres), pasando por las directivas operativas y los patrones transversales. Cada entrada lleva un **estado epistémico**: hipótesis en prueba, observación confirmada o directiva validada por las pruebas acumuladas a lo largo de las conversaciones.

Más allá de la escritura, el diario **se mide a sí mismo**. En cada turno, LIA mira las directivas que aplicó en el turno anterior y lee tu reacción en el turno actual: si confirmaste, el contador de pruebas sube; si contestaste, el contador de contradicciones sube. Con el tiempo, las hipótesis falsas se rebajan silenciosamente, las buenas intuiciones se promueven, los patrones transversales emergen por agrupación activa.

De esta estratificación emerge un **retrato de usuario compilado**: tu voz, tu ritmo, tus contextos, tus contradicciones, tus zonas de sombra. Viaja con LIA dondequiera que hable — conversación, voz, recordatorios, notificaciones proactivas, ReAct, fallback — para que el asistente no «olvide quién eres» según la superficie por la que habla.

Es una forma de introspección artificial — el asistente que reflexiona sobre sus interacciones, mide su propia utilidad y desarrolla una comprensión matizada de ti. Mantienes el control total: lectura por tema o por nivel, edición, señalización de un problema en el retrato, activación de una consolidación bajo demanda. El retrato mismo nunca se edita directamente — es una voz de síntesis, corregida mediante palancas indirectas para preservar su coherencia.

### 7.4. La seguridad emocional

Cuando se activa un recuerdo con una alta carga emocional negativa, LIA cambia automáticamente a modo protector: nunca bromear, nunca minimizar, nunca banalizar. El asistente adapta su comportamiento a la realidad emocional de la persona — no un tratamiento uniforme para todos.

### 7.5. El conocimiento de sí mismo

LIA dispone de una base de conocimientos integrada sobre sus propias funcionalidades, lo que le permite responder preguntas sobre lo que sabe hacer, cómo funciona y cuáles son sus límites.

---

## 8. Fiabilidad en producción

### 8.1. El verdadero desafío de la IA agéntica

La gran mayoría de los proyectos de IA agéntica nunca llegan a producción. Costes descontrolados, comportamiento no determinista, ausencia de trazas de auditoría, coordinación deficiente entre agentes. LIA ha resuelto estos problemas — y funciona en producción 24/7 sobre una Raspberry Pi. Y tus datos sobreviven a los incidentes: la base de datos se respalda automáticamente cada noche, y el procedimiento de restauración no es teórico — está probado.

Lo que « calidad de producción » significa aquí se reduce a una exigencia: los modos de fallo se anticipan **por naturaleza**, no se descubren de uno en uno. Una función que nadie encuentra no existe — la alcanzabilidad de la interfaz se mide por tanto igual que la disponibilidad del servidor, anchura por anchura y en los seis idiomas. Una función que falla en silencio tampoco existe: tres causas sin relación pueden producir el mismo síntoma, « no pasa nada », y cada una debe nombrarse.

Los fallos más costosos son los que no gritan. Un defecto intermitente, que se cierra concluyendo « fue pasajero ». Una guardia que observa la señal equivocada y sigue en verde precisamente por eso. Un fallo que solo degrada la calidad sin levantar nunca un error. Y una cifra: un recuento mostrado es una afirmación — es exacto, o no existe. Cada una de estas familias tiene su medición propia, porque ninguna se anuncia sola.

### 8.2. Una stack de observabilidad profesional

LIA incorpora una observabilidad de grado producción:

| Herramienta | Rol |
| --- | --- |
| **Prometheus** | Métricas de sistema y de negocio |
| **Grafana** | Dashboards de monitorización en tiempo real |
| **Tempo** | Trazas distribuidas de extremo a extremo |
| **Loki** | Agregación de logs estructurados |
| **Langfuse** | Tracing especializado de llamadas LLM |
| **Alertmanager** | Alertas por correo sobre señales vitales, runbooks enlazados |

Cada solicitud se traza de extremo a extremo, cada llamada LLM se mide, cada error se contextualiza. No es un monitoring añadido a posteriori — es una **decisión arquitectónica fundamental** documentada en los Architecture Decision Records del proyecto.

### 8.3. Un pipeline anti-alucinación

El sistema de respuesta dispone de un mecanismo anti-alucinación en tres capas: formateo de datos con límites explícitos, directivas que imponen el uso exclusivo de datos verificados, y gestión de casos límite. El LLM está obligado a sintetizar únicamente lo que proviene de los resultados reales de las herramientas.

### 8.4. Human-in-the-Loop en 6 niveles

LIA no rechaza las acciones sensibles — te las **presenta** con el nivel de detalle adecuado: aprobación de plan, clarificación, revisión de borrador, confirmación destructiva, confirmación de operaciones masivas, revisión de modificaciones. Cada aprobación alimenta el aprendizaje — el sistema se acelera con el tiempo. Y la promesa se cumple al pie de la letra: lo que apruebas — tras una, dos o diez retoques — es **exactamente** lo que se ejecuta, nunca una versión regenerada a escondidas.

### 8.5. Tus respuestas no te necesitan

Envía una pregunta, cierra la pestaña, vete. La generación continúa en el servidor, y la respuesta te espera en la conversación — o se reanuda en directo, exactamente donde estaba, si vuelves mientras aún se está escribiendo. Nada que hacer, nada que configurar: la continuidad es el comportamiento por defecto. Y cuando eres tú quien cambia de opinión, un botón de stop interrumpe la generación en un segundo — lo ya escrito permanece en pantalla, honestamente marcado como interrumpido. Un asistente fiable no es solo el que responde bien: es el que termina lo que empieza.

### 8.6. Nada se ejecuta a tus espaldas

Un asistente capaz de actuar es un asistente capaz de *equivocarse*. Dos reglas lo hacen aceptable.

Primero, **nada toca tu servidor sin tu sí** — y la confirmación muestra todo lo que se va a enviar, incluidas las instrucciones que LIA se escribió a sí misma. Un resumen que no puedes leer entero no es una confirmación, es un trámite. El permiso se vuelve a comprobar en el momento en que arranca la acción, no solo cuando la pediste.

Segundo, **lo que se ejecuta, se ejecuta en una caja sellada**. El código de una skill corre en un contenedor creado para esa única ejecución y destruido justo después: sin red, sin acceso a tus archivos, sin claves, sin forma de alcanzar la máquina que hay debajo. Si esa caja no puede construirse, el script sencillamente no corre — ningún repliegue silencioso a un modo más débil. Se instala una skill por lo que produce, no por la confianza que habría que dar a su autor.

---

Esta exigencia vale también para lo que LIA **afirma**. Una respuesta debe apoyarse en datos realmente obtenidos, nunca en el recuerdo de una formulación anterior; y cuando una información nunca se consiguió, declararla ausente vale más que reconstruir algo plausible. Es una restricción de diseño más que una cuestión de estilo: las entidades obtenidas recientemente se reinyectan explícitamente en el contexto de respuesta, y inventar un atributo de entidad está prohibido a nivel de prompt. Un error factual plausible cuesta más que un «no lo sé».

La coherencia visual responde a la misma exigencia. Una acción tiene la misma forma en todas partes o en ninguna; un código de color que el puntero debe revelar no es un código, es un secreto; el gris queda reservado a lo inactivo — un estado vivo lleva su color. Estas reglas no son gustos: cada una está escrita, equipada y custodiada por un test, porque el esfuerzo de lectura pertenece al sistema, no a la persona que lo usa.

## 9. Apertura radical

### 9.1. Cero lock-in

ChatGPT te ata a OpenAI. Gemini a Google. Copilot a Microsoft.

LIA te conecta a **7 proveedores de IA simultáneamente**: OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen y Ollama (modelos locales). Puedes combinarlos: OpenAI para la planificación, Anthropic para la respuesta, DeepSeek para las tareas en segundo plano — todo configurable desde la interfaz de administración, en un clic.

Si un proveedor cambia sus tarifas o degrada su servicio, cambias al instante. Sin dependencias, sin trampas.

### 9.2. Estándares abiertos

| Estándar | Uso en LIA |
| --- | --- |
| **MCP** (Model Context Protocol) | Conexión de herramientas externas por usuario |
| **agentskills.io** | Skills inyectables con progressive disclosure |
| **Agent Plugins** (estándar abierto) | Plugins portátiles que agrupan skills + servidores MCP, instalación en un paso |
| **OAuth 2.1 + PKCE** | Autenticación para todos los conectores |
| **OpenTelemetry** | Observabilidad estandarizada |
| **AGPL-3.0** | Código fuente completo, auditable, modificable |

### 9.3. Extensibilidad

Cada usuario puede conectar sus propios servidores MCP, ampliando las capacidades de LIA mucho más allá de las herramientas integradas. El cliente habla las dos generaciones del protocolo — la nueva revisión sin estado y el handshake clásico, elegidos automáticamente por servidor —, de modo que la apertura nunca cuesta compatibilidad. Los Skills (estándar agentskills.io) permiten inyectar instrucciones expertas en lenguaje natural — con un generador de Skills integrado que los crea mediante un diálogo guiado y los instala directamente en tus skills, listos para usar. Un Skill también puede devolver un **frame HTML interactivo** (mapa, panel, calendario, conversor...) o una **imagen** (QR code, gráfico) directamente en el chat, aislado bajo una CSP estricta, con tema e idioma sincronizados automáticamente.

Esta apertura tiene un formato de paquete: LIA habla el estándar abierto **Agent Plugins** (agent-plugins.org), el formato de plugin portátil dirigido por AWS, Microsoft, OpenAI, Cursor y Vercel y adoptado por ChatGPT, Codex, Cursor, GitHub Copilot, Kiro y VS Code. Un plugin que agrupa skills y servidores MCP se instala en LIA en un paso — desde un zip o un enlace https — con un informe completo por componente de lo instalado, lo omitido (y por qué) o lo eliminado, y se desinstala con la misma limpieza: todo lo que aportó se va con él. La interoperabilidad aquí es una convicción, no una función: lo que construyes o adoptas en cualquier lugar del ecosistema es tuyo y te acompaña.


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

Cómo se construye LIA — una IA que escribe el código, un humano que dirige, revisa y audita — se cuenta en detalle en nuestro [informe de experiencia](/es/story).

**Your Life. Your AI. Your Rules.**

### El trabajo invisible se muestra, el aprendizaje es administrable

Un asistente proactivo trabaja cuando no miras — y ese trabajo también debe verse. La página **Actividad** reúne todo lo que LIA hizo por iniciativa propia en un único hilo cronológico, con totales exactos y fallos declarados: nunca «aproximadamente», nunca un silencio. La misma exigencia gobierna lo que el asistente aprende de ti: cada regla duradera («responde más corto», «no me propongas eso por la noche») es una memoria **visible, editable y eliminable** — y cuando un hecho cambia, el antiguo no se borra: se archiva detrás del nuevo, para que corregir nunca sea reescribir la historia. Las rutinas que LIA propone gestionar esperan tu visto bueno en una bandeja dedicada: aceptar prellena el chat, nada se envía sin ti, rechazar le enseña a insistir menos.
