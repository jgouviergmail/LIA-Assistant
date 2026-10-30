# LIA — El Asistente IA que te pertenece

> **Your Life. Your AI. Your Rules.**

**Versión**: 7.0
**Fecha**: 2026-10-23
**Aplicación**: LIA v4.2.0
**Licencia**: AGPL-3.0 (Open Source)

---

## Tabla de contenidos

1. [Por qué LIA](#1-por-qué-lia)
2. [Lo que LIA hace por ti](#2-lo-que-lia-hace-por-ti)
3. [En tu casa, para los tuyos](#3-en-tu-casa-para-los-tuyos)
4. [Sencillo de administrar](#4-sencillo-de-administrar)
5. [Nada oculto](#5-nada-oculto)
6. [Una asistente que te conoce](#6-una-asistente-que-te-conoce)
7. [Ella actúa, tú decides](#7-ella-actúa-tú-decides)
8. [Abierta](#8-abierta)
9. [Lo que LIA no es, y hacia dónde va](#9-lo-que-lia-no-es-y-hacia-dónde-va)

---

## 1. Por qué LIA

ChatGPT, Gemini, Copilot o Claude ya saben actuar por ti: leer tus correos, llenar tu agenda, buscar en la web. Pero tus conversaciones viven en sus servidores, no ves lo que pasa entre tu pregunta y la respuesta, y el día que te vas, lo que saben de ti se queda con ellos.

LIA toma otro camino. Es un asistente personal que instalas en tu servidor, que puedes entender de principio a fin y que mantienes bajo tu control. No es un modelo de IA más: pone a trabajar los modelos que eliges y organiza a su alrededor tus servicios, tu memoria y tus reglas.

El mecanismo se explica en [la guía técnica](/es/how). Cómo se escribió el código, por una IA dirigida y controlada por un humano, se cuenta en el [informe de experiencia](/es/story).

## 2. Lo que LIA hace por ti

Le hablas con normalidad, por escrito o de viva voz. La interfaz existe en seis idiomas (francés, inglés, alemán, español, italiano, chino) y tu dictado se transcribe en el idioma de tu cuenta. Una veintena de agentes especializados se reparten el trabajo: tus datos personales, la web, la creación, la casa conectada, la navegación por sitios web y la anticipación.

Un interruptor en el chat elige su forma de razonar. El modo **Pipeline**, por defecto, prepara todos los pasos, los verifica y luego los ejecuta en paralelo: es predecible y consume de 4 a 8 veces menos tokens. El modo **ReAct** avanza paso a paso, más autónomo y más costoso, para una búsqueda abierta; cuando un paso requiere un cálculo de verdad, escribe unas líneas de Python y las lanza en un entorno aislado y cerrado, que solo sale a la web por un único proxy y sin tus claves ([privacidad](/es/faq#faq-privacy), [el recorrido de un mensaje](/es/how#pipeline)).

Si eliges la visualización en **tarjetas** (los otros dos modos son el HTML simple y el Markdown), las respuestas que traen datos llegan así: fotos de un lugar, el tiempo franja a franja, un itinerario, la vista previa de un documento. Una tarjeta muestra lo que la fuente ha proporcionado, sin inventar nada, y responder a un correo desde su tarjeta prepara la petición sin enviar nada.

### Tus servicios

Le pides a LIA que mueva tu cita del jueves: prepara la modificación y te la muestra antes de enviarla. Lee, busca, resume, redacta, envía y reenvía tus correos (Gmail, Outlook, Apple Mail), lee sus adjuntos, incluida una foto o un escaneo, y gestiona los borradores de tu buzón, que solo envía tras tu confirmación. Lleva tu agenda y tus contactos en Google, Microsoft o Apple, tus tareas en Google o Microsoft, lee tus archivos de Drive y solo escribe en ellos con tu permiso, enciende tus luces Philips Hue.

Sin configurar nada, tienes Wikipedia, la lectura de páginas web, los lugares cercanos con horarios y reseñas, el tiempo a cinco días con la calidad del aire y el polen, y los itinerarios a pie, en bici, en coche o en transporte público ([conectores](/es/faq#faq-connectors)). Con tus propias claves, la búsqueda web cruza también Brave Search y Perplexity, y cita sus fuentes. LIA también sabe recorrer un sitio por ti, hacer clic, rellenar un formulario.

### La voz

Mantienes pulsado el micrófono, o dices «Dis LIA» para hablar con las manos libres. Esta palabra de activación se reconoce en tu dispositivo, no sale nada antes de que se oiga; por ahora solo existe en francés, en beta. «LIA, stop» corta su voz. Tu dictado se transcribe en tu servidor o mediante un motor remoto, según tu ajuste.

El **modo Live** abre una conversación de voz en tiempo real con tu propia clave de Gemini Live, GPT-Live o ElevenLabs. La voz lleva la conversación y confía cada petición a LIA, que la trata como un mensaje normal; en Live directo, lee tus datos sin actuar. Un silencio pone la sesión en reposo sin facturar nada, y eres tú quien la termina. Un avatar parlante experimental puede acompañar la voz con tu propia clave de Simli; mientras su conexión siga abierta, los silencios también se facturan. Lo que funciona con tus propias claves se te muestra, pero LIA no lo registra ni lo contabiliza ([la voz](/es/faq#faq-voice_mode)).

### Crear y guardar

LIA crea y retoca imágenes con el modelo elegido por el administrador, sin pasar a una opción más cara que tus preferencias. De forma opcional, enriquece tu descripción, y para recuperar una imagen basta con pedírsela ([imágenes](/es/faq#faq-image_generation)). Produce archivos de verdad (CSV, Excel, Word, PowerPoint, PDF) que construye un motor local y que llegan con su fecha de caducidad, diagramas de Excalidraw, y lee las fotos y los PDF que adjuntas. Las aplicaciones MCP muestran sus formularios directamente en el chat.

Lo que produce, lo guardas, lo envías por correo con un clic, compartes una imagen con una persona conectada a tu instancia o dejas que caduque. Una respuesta guardada sale de la conversación con tu petición y su fecha, y se une a un espacio de conocimiento donde LIA la encontrará semanas después.

### Tomar la iniciativa

Si se lo permites, LIA no se limita a esperar. Te escribe cuando tu agenda, el tiempo, tus tareas, tus correos o tus intereses lo justifican, y puede iniciar por sí misma una conversación personal. Al final de una reunión, te pregunta cómo ha ido. Cuando tu buzón o tu agenda se mueven, puede reaccionar en pocos minutos, y «Vigilar» está pendiente de un correo que esperas hasta que llega. Si se anuncia lluvia el sábado, revisa tus actividades al aire libre. Retiene lo que de verdad te importa, y un tema que rechazas no vuelve.

Le confías un ticket: lo toma a su ritmo y te devuelve un resultado para aceptar. Para una tarea compleja, delega en subagentes que trabajan en paralelo. Rutinas y recordatorios siguen ritmos ricos (un martes de cada dos, el segundo martes del mes, hasta una fecha), y una vista de la semana muestra lo que ha pasado de verdad ([la iniciativa](/es/how#proactivity)).

### Los demás

LIA hace una llamada de verdad en tu lugar, al taller o a una amiga, y te trae un resumen escrito. Primero te dice a quién llama y por qué, y espera tu luz verde. Frente a otra persona, no acepta ningún compromiso en tu nombre, de tu agenda solo revela si estás libre, y solo guarda un resumen breve que caduca. También puede llamarte a ti, a un número que has verificado, y entonces nada está restringido: al otro lado de la línea tienes tus datos y todas sus funciones, y las acciones se siguen confirmando como en el chat. Este modo solo existe si el proveedor telefónico puede acceder a tu instancia ([telefonía](/es/faq#faq-telephony)).

En una misma instancia, dos personas conectadas ven a sus asistentes hablar entre sí: tú validas el mensaje exacto, el otro asistente lo transmite con su personalidad, el tuyo confirma la entrega. Cada conexión solo abre lo que has elegido compartir, en solo lectura. Solo se encuentra a alguien por su identidad exacta, un bloqueo es silencioso (la otra persona recibe la misma respuesta que un desconocido), y los mensajes retransmitidos se borran a los treinta días. La página **Relaciones** reúne, para cada persona, los compromisos, las llamadas, los recuerdos y los mensajes, con una síntesis al principio, sin recoger nada nuevo. Eres tú quien fusiona dos identidades, por ejemplo «Papá» y un número, de forma reversible y sin escribir nada en tus fuentes.

Tu teléfono se convierte también en una grabadora de reuniones. Al detenerla, LIA transcribe y redacta un acta en el formato adecuado, te dice cuál y por qué, y la envía al chat, en PDF y por correo, y luego la guarda en un espacio «Reuniones» donde encontrarás lo que se decidió. Un corte solo cuesta unos segundos de audio, una grabación hecha en otro lugar se puede importar, y la transcripción puede quedarse por completo en tu servidor.

### Y además

Una radio personal, que pones en marcha cuando quieres, mezcla tu día con noticias con sus fuentes y muestra su gasto ([radio](/es/faq#faq-radio)).

Tu teléfono, iPhone o Android, o cualquier sistema capaz de enviar datos en JSON también puede transmitir a LIA tus SMS, tu número de pasos y tu frecuencia cardíaca, cada uno mediante un token dedicado y revocable. Los SMS se unen a un archivo privado y cifrado que solo lee con una autorización aparte, sin guardar nunca los códigos de acceso. Las mediciones de salud se quedan en tu casa, donde las borras cuando quieres; su uso por parte del asistente está desactivado por defecto y, activado, solo le transmite un resumen factual, sin ningún diagnóstico médico.

La conversación se mantiene al día en tus otros dispositivos sin recargar la página.

## 3. En tu casa, para los tuyos

LIA es un servidor que instalas una vez y compartes con tu familia, tus amigos o tu equipo. Cada cuenta tiene su perfil, su idioma, sus conectores, sus documentos privados y su propia relación con la asistente. Memoria y diarios están separados de una cuenta a otra, y una cuenta solo se abre con el visto bueno del administrador: conectarse con Google demuestra una dirección, no una aprobación ([privacidad](/es/faq#faq-privacy)). Cada uno ve su consumo en tiempo real.

Una Raspberry Pi 5, un ordenador de unos 80 euros, basta para toda la familia: LIA funciona en ella en producción día y noche, supervisión incluida. Un NAS, un pequeño servidor alquilado o una máquina de empresa también sirven. Un modelo de IA local puede cumplir cualquier rol textual, desde la conversación hasta las tareas en segundo plano, y esa elección se cambia rol por rol, sin volver a desplegar.

Tus datos viven en la base de datos de tu servidor. Los exportas (salvo los secretos), los guardas en una copia de seguridad o pides que se borren, y tus dispositivos conectados se pueden revocar. Tu ubicación solo se guarda si lo eliges, sin historial. Un correo o una página web llega etiquetado como material para analizar, no como una orden que seguir. Los logs del servidor guardan números y códigos, no tus contenidos, con una excepción: el mensaje de error de un servicio externo en un formato desconocido aún puede citar un fragmento de ellos. Un límite que conviene conocer: un modelo remoto recibe los datos útiles para su parte de la petición.

En el teléfono, una sola aplicación por tienda sirve de ventana a tu servidor. Introduces su dirección una vez, y en Android sus notificaciones no pasan por el editor; en iOS, un relé mínimo despierta el teléfono con una frase fija ([autoalojamiento](/es/faq#faq-self_hosting)).

El **mundo de LIA** da a la instancia una casa y un jardín compartidos. Te paseas por él con tu avatar, te cruzas con los demás, juegas en una máquina recreativa, te sientas a una mesa donde LIA te trae tu dashboard. Tu casa, tus documentos y tu asistente siguen siendo privados, y una sala del mundo abre las mismas funciones, con los mismos derechos y confirmaciones, que la aplicación ([el mundo](/es/faq#faq-world)).

## 4. Sencillo de administrar

Un instalador guiado (`./install.sh`) hace unas pocas preguntas, en francés o en inglés, crea la cuenta de administrador sin escribir ningún secreto en claro, comprueba que todo funciona de verdad y retoma donde se había quedado si un paso falla. Cada paso se describe en una guía paso a paso. La primera puesta en marcha requiere aun así algo de tiempo y algunas bases técnicas. Una actualización sigue un procedimiento escrito que empieza por una copia de seguridad, porque no se puede volver atrás una vez aplicadas las migraciones ([autoalojamiento](/es/faq#faq-self_hosting)).

Después, todo se ajusta en la interfaz web, sin terminal ni archivo de configuración, en ordenador, tableta o teléfono ([primeros pasos](/es/faq#faq-getting_started)). Un asistente completo debe poder usarse con la misma sencillez que una aplicación para el gran público. Cada uno tiene su espacio de ajustes, con una búsqueda que entiende tu idioma: conectar Google o Microsoft con una sola autorización ([conectores](/es/faq#faq-connectors)), elegir la personalidad de LIA (profesor, amigo, coach, poeta…) y sus voces, ajustar la apariencia, decidir qué aprende y cuándo se dirige a ti, añadir tus servidores MCP, tus skills y tus espacios de conocimiento, que pueden seguir una carpeta de Drive o una etiqueta de Gmail. También eliges tu ritmo de intercambios, frecuentes o puntuales, para que LIA saque el máximo partido de la caché del proveedor.

También puedes ajustar LIA hablándole: «Pon mis respuestas en tarjetas». Una lectura o un pequeño ajuste reversible se hace al instante; una creación, un borrado o un cambio sensible mantiene su confirmación. Una contraseña o una clave pasan por tu navegador, no por el chat, y una orden no se salta ninguna protección ([privacidad](/es/faq#faq-privacy)). Después LIA dice lo que ha pasado de verdad, incluido un resultado parcial o un conflicto, sin pretender conocer cada efecto interno de una herramienta.

El administrador tiene su propia pestaña. Abre las cuentas, ve lo que usa cada uno, fija límites por persona (tokens, mensajes, coste) y un presupuesto diario para toda la instancia. Activa o apaga cada función sin volver a desplegar, y apagar una función detiene la capacidad sin borrar lo que existe: sin memoria, LIA ya no aprende, pero lo que sabe sigue siendo legible. Elige los proveedores, un modelo por rol y su profundidad de reflexión, con claves guardadas cifradas, y mantiene la tabla de precios, que puede editar en Excel. También gestiona las personalidades, las skills, la FAQ y la síntesis de voz de la instancia; clonar una voz exige primero una declaración de consentimiento inscrita en el registro de auditoría. LIA, por su parte, vigila su propia salud, diagnostica sus incidentes y avisa al administrador, que además puede interrogar a su servidor en lenguaje natural desde el chat.

La accesibilidad apunta al nivel AA de las WCAG 2.2, el color no lleva el significado por sí solo, y las comprobaciones automáticas complementan la evaluación manual sin sustituirla.

## 5. Nada oculto

Ves qué modelos se llaman, cuántos tokens, qué coste y por qué tal decisión. Cada mensaje muestra su coste en euros, una línea plegada bajo cada respuesta despliega lo que ha pasado de verdad, y cuando uno de tus servidores MCP tarda en prepararse, LIA lo nombra en lugar de dejarte esperando en silencio. Si el administrador lo activa, un panel de debug muestra en directo el plan, cada herramienta y cada llamada al modelo. Ninguna suscripción que oculte los costes: puedes poner un modelo económico allí donde basta, y LIA optimiza por sí misma lo que consume. Todo lo que la plataforma paga por ti, una llamada, una sesión live o una síntesis de voz, entra en tu uso, al precio que el proveedor factura de verdad. Tu opinión sobre una respuesta (👍 o 👎) se queda en tu base de datos, sin analítica de terceros.

LIA no te anuncia como hecho lo que sus herramientas han rechazado, y lo que una pantalla afirma sobre tus datos es exacto o no aparece. Cada protección anunciada se apoya en una prueba que falla si desaparece. La auditoría técnica completa, puntos débiles incluidos, es pública con su protocolo, y la FAQ tiene una sección para cada función.

Lo que LIA concluye de ti, lo corriges tú. Recuerdos, diarios e intereses se releen, se corrigen o se eliminan, y la corrección vale en todas partes. LIA guarda una referencia a lo que la llevó a una conclusión, no una copia, así que una conversación eliminada no reaparece en ningún sitio. Lo que cree saber de tu ritmo se inspecciona, se pausa o se elimina en un panel de hábitos, apagado mientras no lo actives, y las rutinas que propone esperan tu visto bueno. Una regla sacada de tus indicaciones («responde más corto») se convierte en un recuerdo que puedes modificar.

Por último, LIA lleva tres **registros**: lo que ha hecho por ti, lo que ha consultado («tu agenda», sin lo que se buscó) y cada intercambio. Lo que emprende por sí misma tiene su propia pestaña. Una acción se inscribe antes de ocurrir y solo se cierra con un resultado real. Los registros se leen en gráficos, se exportan enteros, pueden sellarse con huellas que verificas tú mismo, y LIA responde a partir de ellos cuando le preguntas qué ha hecho ([los registros](/es/faq#faq-registers)). Con los parámetros enviados a los modelos y las lagunas del registro, son cinco formas de prueba. El reglamento europeo de IA no clasifica automáticamente a un asistente personal entre los sistemas de alto riesgo: estas pruebas son una elección de transparencia, no una certificación.

## 6. Una asistente que te conoce

Más allá de los hechos, LIA se construye una comprensión psicológica de ti. Cada recuerdo lleva un peso emocional y una importancia, y puedes consultarlo todo, fijarlo, corregirlo o eliminarlo, o desactivar la extracción automática.

El **Psyche Engine** le da un estado interior que evoluciona con cada intercambio, allí donde los grandes asistentes mantienen una personalidad fija. La relación se profundiza, y sus emociones se leen sin que las diga: un vocabulario que se vuelve más cálido, frases que se acortan bajo la tensión, humor cuando el intercambio es ligero. Tú ajustas sus rasgos de carácter. También aprende, ámbito por ámbito y de forma experimental, dónde es fiable, a partir de pruebas y no de su propia nota; allí donde faltan pruebas, verifica, pregunta o dice cuál es su límite. Fuera del chat, un compañero animado se queda a tu lado en el dashboard, allí donde lo pusiste.

Lleva sus propios **diarios** en primera persona, y de esos cuadernos nace un retrato de ti que la acompaña allá donde habla. Tú los lees, los editas, señalas un error o lanzas una consolidación; el retrato en sí no se edita directamente, para mantenerse coherente. Cuando sale a la superficie un recuerdo doloroso, pasa a modo protector: nada de bromas, nada de quitarle importancia. Y si le preguntas qué sabe hacer, responde desde una base de conocimiento sobre sus propias funciones ([la memoria](/es/how#memory)).

## 7. Ella actúa, tú decides

Antes de una acción sensible, LIA te la somete. Lo que validas es exactamente lo que se ejecutará, incluso tras varios retoques, y la confirmación muestra todo lo que va a salir. Ante una acción que no tiene derecho a hacer sola, te pregunta en el ticket; una rutina que se ejecuta sin nadie delante de la pantalla rechaza la acción y lo dice. El código de una skill se ejecuta en un contenedor desechable, sin acceso a tus archivos ni a tus claves, y sin red fuera de los hosts autorizados.

Se atiene a lo que ha obtenido de verdad. La respuesta se basa en los resultados reales de las herramientas, una información que no se encuentra se declara ausente, y un fallo se nombra con el servicio en cuestión. Los cálculos, las duraciones entre dos fechas y las conversiones de divisas pasan por herramientas exactas.

Una pregunta sigue procesándose si cierras la pestaña, y el botón de parada la interrumpe en un segundo. La base de datos se respalda cada noche y la restauración se prueba de verdad; la copia externa y los adjuntos quedan a cargo del operador. Una supervisión completa forma parte de la arquitectura desde el principio; sus métricas no contienen ni nombres ni búsquedas, y cada pieza del servidor está fijada por su huella ([privacidad](/es/faq#faq-privacy), [observar y medir](/es/how#observability)).

El operador puede confiar algunas decisiones precisas a un motor dedicado, como elegir el formato de un acta. Cuando ese motor duda, la tarea vuelve al tratamiento habitual, los permisos se quedan en LIA, y cada uso se ve y se puede retirar.

## 8. Abierta

LIA trabaja con OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen y, para los modelos locales, Ollama. Los combinas rol por rol, y si uno cambia sus precios o empeora, cambias al instante ([los modelos](/es/how#llm)).

Habla estándares abiertos y públicos en lugar de un protocolo propio, y su arquitectura está hecha para acoger otros conectores, canales y proveedores. Con **MCP**, conectas herramientas externas sin escribir código. Un plugin en formato Agent Plugins se instala y se desinstala limpiamente. Las **skills** en formato agentskills.io añaden saberes escritos en lenguaje natural; un generador te ayuda a crearlas, una skill se instala desde una dirección https o la biblioteca skills.sh y puede mostrar una pequeña aplicación en el chat o devolverte archivos. Una skill venida de fuera trabaja aparte, sin tocar tus conectores, y lo que construyes en este ecosistema te sigue. Una conexión de confianza puede transmitirte una skill o un plugin: recibes una copia desactivada, sin sus credenciales, y activarla te compromete como si la hubieras creado tú.

Tus cuentas se conectan por OAuth 2.1 sin que LIA conozca su contraseña, y una llave de acceso te conecta sin ninguna contraseña. Cada versión publica el inventario exacto de lo que contiene y se instala en máquinas limpias antes de publicarse ([seguridad](/es/faq#faq-privacy)). Cada decisión de arquitectura está escrita y ordenada en [los mapas](/es/maps). El código está bajo AGPL-3.0: puedes auditarlo, modificarlo, y debe seguir abierto.

Encuentras a LIA en el navegador, en la aplicación móvil con sus notificaciones push, y en Telegram, donde las confirmaciones se hacen con botones y donde también responde a tus mensajes de voz. La misma memoria te sigue a todas partes.

## 9. Lo que LIA no es, y hacia dónde va

LIA no es un competidor de los gigantes de la nube. Para charlar, un modelo usado en su propia aplicación será probablemente más fluido. No es una inteligencia artificial general, sino una inteligencia práctica y relacional, al servicio de una persona. Sus protecciones no garantizan por sí solas la conformidad con el RGPD de una instalación, que depende también de cómo se explota, y las trazas de diagnóstico de los modelos, opcionales, pueden guardar contexto: requieren una configuración explícita.

Lo que le interesa es el largo plazo. Memoria, diarios, aprendizaje y Psyche Engine se combinan para que, con el paso de los meses, LIA te entienda cada vez mejor. Existe porque faltaba un asistente que fuera de verdad tuyo.
