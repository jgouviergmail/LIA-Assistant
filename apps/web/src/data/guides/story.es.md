# Dirigir una IA que programa

> Informe de experiencia — un sistema completo, del diseño a la producción.

**Versión**: 3.0
**Fecha**: 2026-10-23
**Aplicación**: LIA v4.2.0
**Licencia**: AGPL-3.0 (Open Source)

---

## 1. Lo esencial

LIA es un asistente de IA multiagente completo. Tiene conectores de negocio, habla, recuerda, pone en contacto a sus usuarios entre sí y funciona en seis idiomas. La diseñé, dirigí su desarrollo y la opero en producción de forma continua, como proyecto personal.

Casi todo el código lo escribió una IA. Mi trabajo consistió en dirigirla: un referencial de ingeniería escrito, controles automáticos que bloquean lo que no cumple las reglas, una revisión de cada cambio y auditorías periódicas. El resultado se mide: la última auditoría técnica da **7,9/10** sobre 24 perímetros. El repositorio es open source, y el informe completo de la auditoría es público, con sus puntos fuertes y sus debilidades, que asumo.

| Indicador | Valor |
| --- | --- |
| Código escrito por una IA, dirigida, encuadrada y controlada | **≈ 100 %** |
| Líneas de código fuente (sin tests), repartidas en 60 paquetes de dominio backend | **1.059.000+** |
| Pruebas automatizadas inventariadas, en suites adaptadas al commit y a la entrega | **69.000+** |
| Decisiones de arquitectura documentadas (ADR) | **364** |
| Versiones entregadas a ritmo regular | **292** |
| Idiomas, con una paridad verificada automáticamente | **6** |
| Auditoría técnica sobre 24 perímetros | **7,9/10** |

Lo que saco en claro: el desarrollo asistido por IA ya se puede industrializar. Lo que lo limita no es la herramienta, sino el marco de dirección que se le da.

Apliqué la misma disciplina al producto. Cuando LIA confía una pequeña decisión a un modelo, por ejemplo elegir un recorrido o un formato, limita las opciones posibles, mide lo que cuesta y conserva la autoridad para comprobar y confirmar el resultado. Estas decisiones son opcionales, y la confianza de un modelo nunca se convierte en un permiso.

Las funciones pensadas para el largo plazo también dejan ver sus límites. Una decisión se puede recuperar en el acta completa de una reunión. Un saber hacer reutilizable se puede transmitir a una persona de confianza: una capacidad compartida llega desactivada, sin las credenciales de quien la envía. LIA puede evaluar un correo, pero esa evaluación sigue siendo un indicio y no demuestra que el correo sea seguro. Puede situar en un mismo mapa los lugares que propone; abrir ese mapa interactivo sigue siendo decisión de la persona, y su coste se muestra. Un lugar elegido en el mapa ofrece sus detalles y una ruta, facturada una sola vez y contabilizada.

LIA también puede abrir por su cuenta una conversación personal, pero solo en las horas, a partir de las fuentes y sobre los temas que la persona ha permitido. Muestra por qué escribe, en qué contexto se apoya y cuánto cuesta, y cuatro reacciones permiten responderle. Los SMS que reenvía un teléfono se suman a un archivo privado, que la asistente solo lee con un consentimiento aparte.

## 2. El enfoque

La IA generativa cambia lo que producen los equipos, y también la forma en que lo producen. Sobre estas dos cuestiones, no quería formarme una opinión a partir de los discursos del mercado. Preferí enfrentarme yo mismo a la realidad completa de un sistema de IA en producción, con sus costes, sus riesgos, su explotación y su deuda, y a la del desarrollo asistido por IA, llegando hasta el final en ambos casos.

Mi terreno de prácticas es LIA, un asistente de IA conversacional multiagente, autoalojado y multilingüe. Gestiona el correo, la agenda, los contactos y los archivos en Google, Apple y Microsoft, ofrece una interfaz de voz en tiempo real, una memoria a largo plazo y la búsqueda en documentos, y la encarna un personaje animado.

Me impuse unas restricciones: trabajar solo, fuera de mi tiempo de trabajo, con un presupuesto de hardware mínimo, y confiar todo el desarrollo a la IA. Por tanto, este proyecto no mide lo que una persona puede producir deprisa. Mide lo que una dirección exigente obtiene de una IA correctamente encuadrada.

*Base técnica: FastAPI · Next.js/React · LangGraph (orquestación de agentes) · PostgreSQL · Redis · Docker · Prometheus/Grafana/Loki/Tempo · 7 proveedores de modelos de IA integrados.*

## 3. El método

Cuatro dispositivos han sostenido este proyecto, y ninguno es una herramienta: son cuatro actos de gestión. Una IA que programa produce rápido y en volumen, pero solo produce calidad bajo restricciones, y fijar esas restricciones es un trabajo de dirección.

- **Un referencial escrito**, como para un equipo. Fija las reglas de arquitectura, las convenciones, los patrones impuestos con su ejemplo de referencia en el código y las trampas ya conocidas. Está versionado en el repositorio, y cada entrega debe ajustarse a él.
- **Controles automáticos bloqueantes**. Cada regla importante va acompañada de un control que rechaza el commit no conforme: tipado estricto, análisis del código, detección a medida de los bugs que se repiten, paridad de los seis idiomas, batería de tests completa. El nivel de exigencia no depende ni de la vigilancia del momento ni de la buena voluntad de la IA.
- **Una revisión que decide**. Nada entra sin un ciclo fijo: análisis de impacto, propuesta, validación explícita, implementación, verificación. La IA propone, yo decido. Las decisiones importantes se registran y se indexan, para que cada «porqué» sobreviva a quien lo escribió.
- **Auditorías que incomodan**. A intervalos regulares, hago reexaminar todo el sistema de forma contradictoria: cada hallazgo se comprueba con pruebas, los falsos positivos se descartan y la remediación se planifica por olas. Es lo que detiene la deriva lenta que ninguna revisión del día a día detecta.

Hoy hago trabajar a varios agentes de desarrollo a la vez sobre el mismo repositorio. Proceden de dos familias de herramientas y cada uno avanza en su tarea, en su propia copia del repositorio (un «árbol de trabajo») o, a veces, en la misma. Lo que los mantiene unidos no es su coordinación, sino el referencial común, con las mismas reglas escritas y los mismos controles automáticos, esas «guardias» que bloquean antes de cualquier entrega lo que no es conforme. Si un agente cambia el nombre de un botón, una guardia recuerda que la ayuda, la búsqueda de los ajustes y el vocabulario que LIA usa para describirse deben seguir el cambio. Como con el código, nada de su trabajo se consolida sobre la base de un resumen. Cada archivo se atribuye a su autor por su huella y por el registro del agente, cada fusión se reproduce en un árbol aislado y después pasa por todos los controles, y una copia de seguridad precede a cada traspaso. La entrega que reúne estas tareas empieza por el inventario de lo que cada uno cambió realmente, nunca por lo que anuncia.

En el producto, una interfaz conversacional resulta útil cuando puede actuar sobre sus propias herramientas: pedir «Cambia mis respuestas a HTML + tarjetas» debe llevar al mismo ajuste que el formulario. La conversación ofrece un camino más sencillo, pero no añade ningún derecho ni ningún permiso implícito. Cuando LIA da cuenta de lo que hace, preparar no es completar: una solicitud en espera, un cambio guardado y un conflicto deben nombrarse cada uno por lo que es. Los compañeros animados hacen visible este trabajo, con diseños originales y expresiones que siguen la actividad, sin hacer pasar una intención por una acción realizada.

El mundo compartido le da a la asistente lugares: una biblioteca para el conocimiento, una sala multimedia para crear, un jardín para explorar en compañía. La verdadera decisión de ingeniería trata de lo que cruza cada frontera. Un avatar público expresa la elección de una persona, sin exponer el contexto de su asistente ni su casa privada. Una sala abre una herramienta que ya existe, sin conceder ningún permiso nuevo. Los mensajes que se intercambian las personas tienen su propia vida útil, limitada y separada del resto. La traducción es una elección y se contabiliza, mientras que los desplazamientos y la representación de la escena no llaman a ningún modelo. En una partida, el servidor confirma cada jugada, y el rival que maneja el ordenador es una búsqueda acotada, no un modelo. Una foto se dibuja a partir de lo que la persona eligió mostrar, nunca se copia de la pantalla. Una interfaz más rica sigue siendo gobernable mientras sus costes, su propiedad y sus confirmaciones conserven el mismo significado.

---

## 4. Los arbitrajes

Estas son tres decisiones estructurantes, entre las 364 documentadas.

La primera trata de la **soberanía**: no quería ninguna dependencia irreversible de un proveedor. Los modelos de IA (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity y modelos locales con Ollama) pasan todos por una misma abstracción, de modo que cada uso puede cambiar de proveedor con un simple cambio de configuración, comparando costes. En cuanto a los servicios, Google, Apple y Microsoft son intercambiables en cada categoría, ya se trate del correo, de la agenda o de los contactos. El autoalojamiento da el control del servidor: los datos de la cuenta se guardan en la instancia y las credenciales de los conectores están cifradas. Aun así, los servicios remotos que la persona elige reciben los datos útiles para su parte de la petición.

La segunda trata de la **economía**: traté el coste de cada petición como un criterio de diseño. Conviven dos modos de ejecución. Un pipeline determinista y económico atiende las peticiones corrientes, y un agente autónomo se encarga de las exploratorias. En los casos estándar, con un servicio equivalente, la diferencia de consumo medida va de 1 a 4-8. Cada llamada se cuenta por token, se valora en euros, se agrega por usuario y por modelo, y está sujeta a cuotas.

El coste también se juega en los detalles: una notificación de dos frases se pide sin razonamiento, porque un modelo que razona por defecto factura su razonamiento dentro del presupuesto de su respuesta. Por defecto, el agente autónomo solo lleva consigo las herramientas que la pregunta requiere, elegidas por relevancia y no por su orden de llegada: ochenta descripciones de herramientas ocupaban la mayor parte de su primera llamada, sin contabilizarse. Por último, cada llamada se valora al precio que el proveedor factura realmente, con tarifas releídas en sus páginas, la escritura en caché facturada a su precio real y las tarifas de horas valle según el día.

La tercera trata del **control del riesgo**: ninguna acción irreversible sin validación humana. Varios niveles de control humano se escalonan según la sensibilidad de la acción, desde la pregunta de aclaración hasta la tarjeta de confirmación antes de actuar. Hice especificar y probar lo que ocurre en caso de interrupción: una validación pendiente sobrevive a un reinicio, sin pérdidas ni doble ejecución. Cuando una petición contiene varias acciones, cada una se presenta por turno, en su propia tarjeta, y el informe dice qué se hizo y para quién.

En las llamadas telefónicas, la tarjeta de confirmación sirve para proteger a un tercero. Cuando LIA llama a la propia persona, a un número que esta ha declarado y verificado con un código leído en voz alta, es la persona quien hace de tarjeta. Para sus llamadas, igual que para una sesión de voz live del navegador abierta con su propia clave de Gemini, OpenAI o ElevenLabs, es ella quien elige el modo: o bien la voz confía cada petición al chat en el momento en que se dice, con sus confirmaciones, o bien lee sola y no actúa sobre nada. Lo que funciona con su clave personal lo factura el proveedor y se muestra una vez, pero no se contabiliza aquí. En cambio, lo que la plataforma paga por ella queda registrado en su cuenta, sea cual sea el camino: un mapa consultado durante una llamada, el tiempo del briefing, una foto mostrada.

Lo que envía un desconocido, un correo o su adjunto, sigue siendo un dato que leer y nunca una instrucción que seguir. Un script escrito por la asistente solo sale a la web por una única puerta, y allí las claves de la persona se intercambian fuera del alcance del script; para un sitio que nadie ha autorizado, LIA pregunta primero a la persona, que tiene tres respuestas posibles: con los datos, sin ellos o de ninguna manera. Cuando el agente autónomo no puede obtener lo que se le pide, lo dice, junto con lo que ha intentado, en lugar de rellenar el hueco. Lo que debe ser exacto, como un importe, una duración o una conversión, lo calcula una herramienta y nunca lo estima el modelo. Lo que sale sin confirmación solo va dirigido a la propia persona, un correo a sí misma o una llamada a su número verificado: el destinatario no es ahí un parámetro, así que nada puede desviarlo. Una competencia escrita en otro lugar, tomada de una biblioteca pública o de un plugin, trabaja aparte: nunca accede a los conectores de la persona y solo contacta con los hosts permitidos. Y una competencia que escribe la IA solo entra en el espacio de la persona cuando esta hace clic.

## 5. La explotación

Piloto este sistema por instrumentos.

- **Observabilidad**: una treintena de paneles cubren la salud de la aplicación, los compromisos de servicio, los costes de IA, el comportamiento de los agentes y la infraestructura. Se apoyan en más de 600 métricas, logs estructurados centralizados y un trazado distribuido de extremo a extremo. Logs, métricas y trazas solo guardan hechos, nunca las palabras ni los nombres de las personas. Hay más de cincuenta procedimientos de explotación escritos, para el diagnóstico, la remediación y la restauración. Los instrumentos llegan hasta los procesos: cada worker de la API publica lo que ocupa en memoria, de modo que el total de un contenedor se lee proceso a proceso. Un instrumento mide también lo que anuncia: la alerta de latencia solo cuenta los turnos que una persona espera, y el informe diario del servidor empieza por lo que ha registrado la supervisión, en lugar de por una instantánea.
- **Autodiagnóstico**: la asistente lee ella misma esta telemetría. Se comprueba a intervalos regulares, guarda la memoria de los incidentes que ha diagnosticado a partir de esos procedimientos y sortea en sus respuestas una avería conocida. Cada diagnóstico muestra las pruebas en las que se basa.
- **Entrega**: despliegue en contenedores, migraciones de esquema automatizadas, imágenes publicadas para dos arquitecturas de hardware (amd64 y arm64).
- **Cadena de suministro**: cada pieza del servidor está fijada por su huella e inventariada en cada versión. Una vigilancia semanal lee los avisos de seguridad que publica cada dependencia, incluidos los que ninguna base pública recoge. Una actualización espera un plazo de prudencia y nunca vuelve atrás, y cada versión se instala en máquinas vírgenes antes de publicarse.
- **Costes**: una infraestructura frugal por elección, con unos 150 € de hardware, ninguna licencia y piezas open source dimensionadas según la necesidad real.
- **Protección de datos**: la seguridad se revisa punto de acceso por punto de acceso, las credenciales de los conectores y las claves de los proveedores están cifradas, y cada cuenta puede exportarse o eliminarse. Las obligaciones del RGPD dependen también de cómo se opere la instancia y de los proveedores elegidos.

El producto hace visibles estas decisiones de ingeniería para la persona que lo usa. La conversación sigue a una persona de un dispositivo a otro sin alterar su lectura. La radio empieza cuando la persona decide escuchar; nombra las noticias en las que se inspira y muestra lo que cuesta. Un archivo generado tiene una vida útil que la persona puede prolongar, si así lo decide. El trabajo programado y las comprobaciones de condiciones tienen cada uno su propio reloj. Son promesas que se pueden observar, respaldadas por fuentes, límites y pruebas, en lugar de la pretensión de adivinar lo que la persona quiere.

La misma regla vale para lo que aún no está a la altura. La palabra de activación «Dis LIA» es un pequeño modelo entrenado sin conexión y medido después en un banco de pruebas cuyos umbrales se publicaron antes del entrenamiento. El modelo francés todavía no los alcanza: por eso se entrega en **beta**, y el producto lo dice, en lugar de bajar el listón para poder escribir «terminado». Una sesión de voz que se duerme tras un silencio no cuesta nada, y solo la persona la termina.

Una presencia visible debe seguir siendo una elección controlada. El avatar Simli, experimental, reutiliza la voz existente y funciona con la clave personal, con una sola salida audible. Al detenerlo, indica si el cierre está confirmado o sigue pendiente. Una conexión abierta puede consumir el plan incluso en silencio; la espera del modo Live la cierra. Los elementos flotantes se adaptan al espacio disponible sin borrar la posición elegida. La validación del avatar con el proveedor y en dispositivos reales está por hacer, y así se dice. El gasto también debe poder demostrarse: cada intento facturado conserva su tarifa y el uso conocido, incluso tras un fallo o una cancelación.

## 6. La prueba

El nivel que anuncia este documento procede de una auditoría técnica completa. Los 24 perímetros están calificados, y cada hallazgo se verifica en el código y luego se contraverifica para descartar los falsos positivos. La auditoría aplica el método del proyecto: se realiza con herramientas de IA, en postura contradictoria, y cada conclusión se apoya en una prueba comprobada en las propias fuentes. La última evaluación, del 25 de octubre de 2026, da **7,9/10** sobre la versión 3.6.0 tal como está registrada en el repositorio, con un perfil que asumo. Sigue a un 7,3 en agosto y, después, a un 8,0 y a una contraauditoría de 7,8 el 22 de octubre. El informe completo es público, con el cuadro de calificaciones, el método, los hallazgos abiertos y el protocolo para reproducirlo: [informe de auditoría completo](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md).

El plan de acción se organiza en olas, cada una con criterios de salida medibles. La primera se entregó y luego se auditó: la auditoría confirmó lo esencial de lo que se había entregado y reabrió un punto. Así rinde cuentas este proyecto: con un nivel medido, desviaciones incluidas, en lugar de un nivel proclamado.

Aprendí a mi costa que una suite de pruebas en verde no demuestra que una funcionalidad haga lo que debe. Solo demuestra que lo que se ha probado se comporta como está escrito. Los defectos que superan los filtros son precisamente aquellos que nunca se les pidió ver: una capacidad que nadie invoca, una cifra que nadie suma, una guardia que reconoce un nombre en lugar de un mecanismo. Casi nunca son errores de código, sino preguntas que nadie había hecho.

De ahí saqué una regla de trabajo: nada se da por bueno antes de haberse ejecutado, con datos reales y por el camino que sigue el usuario. Un componente puede ser correcto y su página estar vacía; un contador puede ser exacto y responder a la pregunta equivocada. Por eso cada entrega termina con una relectura adversarial, hecha en frío, cuyo objetivo no es ejecutar las pruebas sino encontrarle fallos al trabajo allí donde ellas no miran. Los recorridos de la interfaz se ejecutan en cada entrega en Chromium, y cada semana en Firefox y WebKit, con una comprobación automática de accesibilidad, porque un motor más ve lo que los demás dejan pasar. Y una función que pretende mejorar el comportamiento de LIA sigue siendo un piloto mientras una comparación antes/después, sobre un corpus apartado, no lo haya demostrado.

Cada defecto encontrado deja tras de sí una **guardia estructural**: una comprobación al arrancar, un invariante verificado de forma continua o una prueba que falla si reaparece toda la clase del problema. Es la única forma de progreso que sobrevive a quien la escribió: una corrección protege una línea, una guardia protege la regla.

---

## 7. Convicciones

Esto es lo que esta experiencia cambia en mi forma de dirigir.

- El desarrollo asistido por IA se despliega como un **dispositivo de gestión**, y no como una herramienta. Las ganancias de productividad son reales e importantes, pero solo duran si el marco (referencial, controles, revisión, auditoría) se instala antes de generalizarlo. Es en ese orden como hay que introducirlo en una organización.
- La **gobernanza económica** de la IA se juega desde el diseño de los usos. Dos arquitecturas que prestan el mismo servicio pueden diferir en un factor de 4 a 8 en consumo. Esa elección corresponde a la dirección técnica, aguas arriba, porque el control de la factura siempre llega demasiado tarde.
- Entre la prohibición general y la confianza ciega, existe una **vía gobernable**. El control humano graduado se especifica, se prueba y se audita. Es el enfoque que dibujan las exigencias regulatorias, y ya es operativo.
- Un directivo que practica **arbitra mejor**. Hacer o encargar, aceptar una deuda o no, creer o no en la promesa de un proveedor: estas decisiones ganan en acierto cuando uno ha probado la materia por sí mismo. Este proyecto es mi forma de mantener ese contacto con el terreno.

*Proyecto personal, llevado a cabo fuera de toda actividad profesional. Evaluación técnica procedente de la auditoría del 25 de octubre de 2026, con hallazgos contraverificados. Los recuentos estructurales siguen el repositorio; las líneas de código fuente se volvieron a medir el 26 de octubre de 2026. Repositorio: [github.com/jgouviergmail/LIA-Assistant](https://github.com/jgouviergmail/LIA-Assistant).*
