# Dirigir una IA que programa

> Informe de experiencia — un sistema completo, del diseño a la producción.

**Versión**: 1.7
**Fecha**: 2026-08-20
**Aplicación**: LIA v1.30.16
**Licencia**: AGPL-3.0 (Open Source)

---

## 1. Lo esencial

LIA es un asistente de IA multiagente completo — conectores de negocio, voz, memoria, conexiones entre usuarios, seis idiomas — diseñado, desarrollado y operado en producción de forma continua, como proyecto personal.

La casi totalidad del código fue escrita por una IA, bajo dirección humana: un referencial de ingeniería escrito, controles automáticos bloqueantes, revisión sistemática, auditorías recurrentes. El resultado está medido: **8,3/10** en la auditoría técnica sobre 24 perímetros. El repositorio es open source; las conclusiones de la auditoría — fortalezas y debilidades — se asumen y se resumen en este documento.

| Indicador | Valor |
| --- | --- |
| Código escrito por una IA — dirigida, encuadrada, controlada | **≈ 100 %** |
| Líneas de código (sin tests) — 40 dominios funcionales | **520.000** |
| Tests automatizados, ejecutados en cada commit y entrega | **23.900+** |
| Decisiones de arquitectura documentadas (ADR) | **229** |
| Versiones entregadas a ritmo regular | **210** |
| Idiomas, paridad verificada automáticamente | **6** |
| Auditoría técnica sobre 24 perímetros | **8,3/10** |

Convicción de experiencia: el desarrollo asistido por IA es industrializable hoy. El factor limitante no es la herramienta — es el marco de dirección que se le da.

## 2. El enfoque

La IA generativa transforma a la vez lo que los equipos producen y la forma en que lo producen. Sobre ambos temas, no quería fundar mis convicciones en los discursos del mercado: elegí confrontarme con la realidad completa de un sistema de IA en producción — los costes, los riesgos, la explotación, la deuda — y con la realidad del desarrollo asistido por IA, practicándolos hasta el final.

El terreno de ejercicio: LIA, un asistente de IA conversacional multiagente — correo, agenda, contactos y archivos en Google, Apple y Microsoft, interfaz de voz en tiempo real, memoria a largo plazo, búsqueda documental — autoalojado y multilingüe.

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

Tres decisiones estructurantes, entre las 229 documentadas:

**Soberanía y reversibilidad — ninguna dependencia irreversible de proveedor.** Los modelos de IA (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, modelos locales vía Ollama) están detrás de una abstracción única: cada uso puede cambiar de proveedor por configuración, con comparación de costes. Mismo principio del lado del negocio: Google, Apple y Microsoft son intercambiables por categoría funcional. El alojamiento está íntegramente controlado; los datos personales están cifrados y permanecen en la infraestructura.

**Economía de la IA — el coste por petición es un criterio de diseño.** Dos modos de ejecución coexisten: un pipeline determinista y económico para las peticiones corrientes, un modo agente autónomo para las exploratorias — la diferencia de consumo medida va de 1 a 4-8, con servicio equivalente en los casos estándar. Cada llamada se cuenta por token, se valora en euros, se agrega por usuario y por modelo, se gobierna por cuotas.

**Control del riesgo — ninguna acción irreversible sin validación humana.** Seis niveles de control humano, graduados según la sensibilidad de la acción — de la clarificación a la confirmación de las operaciones destructivas. El comportamiento en caso de interrupción está especificado y probado: una validación pendiente sobrevive a los reinicios, sin pérdida ni doble ejecución.

## 5. La explotación

Un sistema que se pilota con instrumentos:

- **Observabilidad**: veinticinco paneles — salud aplicativa, compromisos de servicio, costes de IA, comportamiento de los agentes, infraestructura. Más de 470 métricas; logs estructurados centralizados con filtrado de datos personales; trazado distribuido de extremo a extremo. Unos cuarenta procedimientos de explotación escritos — diagnóstico, remediación, restauración.
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

La prueba también tiene su episodio más instructivo: tres recalibraciones de un simple espaciado, tres «no veo ningún cambio» — y una cadena de entrega probada sana hasta los bytes servidos al navegador. Dos pistas falsas plausibles (caché del navegador, service worker) cayeron una tras otra, hasta la medición que no perdona: en un navegador dirigido, el margen calculado era de 16 píxeles y el espacio dibujado, de 3. La primitiva de etiqueta seguía `inline`, y un elemento inline ignora sus márgenes verticales — el defecto precedía a todo el programa. El arreglo es una palabra, el arbitraje se hizo sobre tres capturas reales, y la regla se volvió doctrina: medir el renderizado antes de sospechar de la entrega.

El detector de hábitos se ganó la confianza del mismo modo: ejecutado sobre datos reales de producción antes de ser creído — y pillado en falta. Una acción programada diaria llevaba sesenta y seis días escribiendo un mensaje «de usuario» a las 07:00; el detector reivindicó el propio horario del planificador como hábito humano. La refutación se convirtió en una lista blanca de sesiones humanas, la ventana fabricada desapareció y los veredictos honestos cayeron por su peso. La regla permanece: probar contra lo real antes de creer el diseño.

El ciclo 1.29.0 añadió un tercer episodio, y este trata de los tests mismos. Cada protección del programa se había entregado con los suyos, todos en verde — y todos con la misma forma: fijaban lo que el código hacía el día de la entrega. Una lista escrita a mano no describe un sistema; describe lo que su autor sabía de él. Así que se reescribieron tres guardas para **recalcular** la protección desde la fuente de verdad en lugar de repetirla. Encontraron tres fallos que ningún test existente podía ver: una síntesis de voz facturada y jamás contada contra el tope de gasto, un inicio de sesión por proveedor que se saltaba por completo la aceptación ya obligatoria de las condiciones, y once rutas de conectores que vinculaban una credencial real sin ninguna protección. Después cada guarda se rompió a propósito, para comprobar que se pone en rojo — porque una guarda a la que nadie ha visto fallar no es más que otra promesa.

El ciclo 1.30.0 documentó una lección de otra naturaleza: una funcionalidad puede estar entregada, cifrada, consentida — y no servir de nada, porque nadie la lee. La última posición conocida existía desde hacía meses; solo las notificaciones proactivas la consultaban. En movimiento, el asistente respondía por tanto desde el domicilio, con aplomo. El diagnóstico vino de los registros de producción, la corrección redujo tres caminos divergentes a una cascada única — y la doctrina de las cuentas exactas se extendió a la posición: una posición fechada se anuncia fechada, «según tu última posición conocida a las 9:30», nunca «estás en». El mismo ciclo recordó que a un mecanismo de sincronización solo se le cree probado contra el motor real: el candado que serializa el primer arranque se interbloqueó con la creación concurrente de índices de PostgreSQL — medido en la tabla de bloqueos del motor, corregido como sondeo no bloqueante y custodiado por un test que prohíbe el regreso de la forma bloqueante.

Más adelante en el mismo ciclo, la página de ajustes — el lugar mismo desde donde se pilota todo esto — dejó su muro de cincuenta acordeones plegados por una carcasa maestro-detalle: un riel permanente de secciones, un panel, una vista general de tarjetas donde cada descripción por fin es visible antes de abrir nada, y una búsqueda que por fin cubre la administración. El rediseño se decidió sobre maquetas interactivas antes de publicar una sola línea, y retiró de paso toda una clase de deriva: la página se renderiza ahora desde las mismas tablas que alimentan la búsqueda y los enlaces profundos — una sección ya no puede existir a medias.

El ciclo se cerró sobre la superficie que debe responder por todas las demás. El mapa de capacidades seguía publicando trece entradas mientras seis capacidades pasaban por delante, y la portada de ajustes sabía decir lo que una sección ES, no lo que contiene. Ambos se corrigieron desde la misma agregación — diecinueve capacidades, una petición, las mismas palabras en las dos pantallas — y el arreglo que importa no es el contenido sino la aserción puesta debajo: la aplicación se niega ahora a arrancar si una nueva capacidad no ha decidido su lugar en el mapa. Es la misma lección que todas las demás aquí — una convención se degrada, un mecanismo no — aplicada esta vez a la página cuyo único oficio era seguir siendo verdadera.

El ciclo 1.30.1 llevó la lógica un paso más allá: auditó la auditoría. Un informe interno concluía que los puestos LLM en streaming no contaban ningún token — mecanismo exacto, conclusión plausible, severidad máxima. La contraauditoría hizo lo que el informe no pudo: preguntar a producción. Quinientas diez llamadas de quinientas diez estaban contadas. El defecto real estaba en otra parte, y era más insidioso: el recuento dependía por completo de la generosidad de un proveedor al que nadie se lo pedía — nada lo solicitaba, nada lo probaba, nada lo vigilaba. La respuesta no fue un parche sino un contrato: cada proveedor declara su modo de recuento, la aplicación se niega a arrancar sin esa declaración, y una llamada de pago sin recuento se convierte en una alerta. El mismo ciclo reparó el contador de acciones del panel, clavado en cero desde siempre por un vocabulario que nadie emitía — historial incluido, reclasificado desde las intenciones archivadas. Porque una cifra mostrada es exacta, o no existe.

El ciclo 1.30.2 aplicó la misma disciplina a lo que nadie mira nunca: los cimientos. Subir el ecosistema de orquestación cinco meses de correcciones pudo haber sido un simple cambio de números; se ejecutó como una operación con pruebas — cada versión validada en un entorno desechable antes de tocar el repositorio, ocho mil quinientos tests ejecutados bajo las versiones objetivo, los puntos de integración privados simulados sin red. Y la auditoría que acompañó la subida encontró lo que las métricas de cobertura escondían: mil setecientas cincuenta líneas de una segunda implementación de la reanudación humana, jamás conectada, mantenida en verde por cincuenta tests. Eliminada, con su decisión de arquitectura registrada. Un sistema escaparate no se juzga solo por lo que muestra — también por lo que se niega a conservar.

El ciclo 1.30.5 nació de un mensaje de usuario de tres líneas: «pedí transmitir un mensaje, recibí una confirmación, no se envió nada». La investigación — logs de producción con marca de tiempo, base de datos, el propio código del contenedor, prueba a prueba — llegó hasta una sola línea: el motor de ejecución sobrescribía el veredicto de cada herramienta con un éxito codificado en duro, y la capa de honestidad diseñada precisamente para nombrar los bloqueos quedaba desarmada por la misma mentira que debía impedir. La corrección es pequeña; el método es el verdadero entregable: cada hipótesis contraverificada antes de escribir una línea, cada corrección precedida de un test que falla, y un asistente que ahora dice la verdad hasta en sus rechazos — con cifras exactas, en los seis idiomas.

El ciclo 1.30.6 dirigió la misma disciplina hacia fuera: hacia el estándar que habla todo el ecosistema. El Model Context Protocol acababa de publicar una revisión que hace el protocolo sin estado, y cuya propia matriz de compatibilidad condena a los clientes antiguos frente a los servidores de nueva generación. El trabajo se llevó como una investigación de conformidad antes que como una migración: la especificación leída requisito a requisito, cada desviación demostrada por simulación antes de cambiar una sola línea, el nuevo SDK ejercitado contra servidores reales de ambas generaciones. LIA habla ahora las dos — la nueva revisión sin estado y el antiguo handshake —, de modo que cada servidor ya configurado sigue funcionando igual mientras los de nueva generación se vuelven accesibles; el flujo OAuth ganó las obligaciones de seguridad de la revisión, cada una con una regla de tolerancia explícita para los registros existentes. Y rechazar una pantalla de consentimiento ya no es una página de error: es una respuesta, reconocida en seis idiomas.

El ciclo 1.30.7 completó el movimiento: después de hablar el protocolo del ecosistema, hablar su formato de paquete. El estándar abierto Agent Plugins — dirigido por AWS, Microsoft, OpenAI, Cursor y Vercel — acababa de dar a todo el ecosistema una forma portátil de enviar juntos skills y servidores MCP, y el trabajo siguió la disciplina ya familiar: el texto normativo leído sección por sección, cada hipótesis de integración probada contra el código por simulación antes de escribir una línea, y luego un cliente construido casi por completo con capas en las que LIA ya confiaba — el importador de skills endurecido, el registro MCP por usuario, el sistema de cuotas. La revisión encontró y eliminó dos bugs reales antes de que llegaran a ejecutarse, y el ciclo de vida completo se probó en runtime contra la base real, dos veces. Lo entregado es discretamente radical: un plugin preparado para ChatGPT o VS Code se instala en LIA sin cambios, informa exactamente de lo que aportó — y de lo que no pudo aportar, con el motivo — y se va sin dejar rastro.

El ciclo 1.30.11 produjo la lección más inesperada: diseñar una exportación puede revelar que el sistema no sabe responder a su propia pregunta. Administrar ciento veinticuatro modelos de IA con un cuadro de diálogo cada vez había dejado de ser sostenible, y la idea era simple — exportar la tabla de tarifas a un libro, corregirla sin conexión, reimportarla. Pero escribirla exigía responder a «¿cuál es la tarifa de este modelo?». No había respuesta: nada imponía una única tarifa activa, y dos rutas de lectura podían devolver precios distintos para el mismo modelo, en el mismo instante, sobre la misma base. Dos errores de facturación llevaban meses corriendo en producción sin que nadie pudiera verlos. Poner orden produjo una regla que trasciende este dominio: una migración nunca inventa un dato de negocio. La regla intuitiva — conservar la fila más reciente — resultó falsa en los cuatro casos reales; por eso la migración fusiona lo estrictamente idéntico y se detiene nombrando el resto, dejando el arbitraje a una persona. El archivo entregado mantiene la misma exigencia: nada se borra implícitamente, la vista previa que se aprueba es la que se escribe, y lo que no cambió no se reescribe.

El ciclo 1.30.16 desplazó la exigencia de prueba a un terreno nuevo: la estética. Dar una mirada al asistente — dos ojos de dibujo animado que observan mientras escribes, se entornan mientras piensa, barren mientras busca y reaccionan al tono de cada respuesta — fue primero un proyecto de animación, donde la mitad del éxito se juega en la fluidez. La disciplina no cambió por ello: todo el comportamiento cabe en un motor puro alimentado por señales que la aplicación ya emitía — la máquina de estados del chat, los pasos de ejecución transmitidos, el motor emocional — sin una llamada de modelo ni un punto de acceso más, cada expresión gobernada por tablas de decisión probadas con relojes y azar inyectados. Y cuando el panel de usuarios no zanjó el estilo, el arbitraje se dictó como todos los demás: sobre pruebas, un tablero interactivo de estilos previsualizados de verdad. El ganador se convirtió en el predeterminado, los demás en una opción de ajustes — y añadir uno nuevo es una entrada de registro, no un proyecto.


## 7. Convicciones

Lo que esta experiencia cambia en una práctica de dirección:

- **El desarrollo asistido por IA se despliega como un dispositivo de gestión, no como una herramienta.** Las ganancias de productividad son reales e importantes; solo duran si el marco — referencial, controles, revisión, auditoría — está instalado antes de la generalización. Es en ese orden en el que hay que introducirlo en una organización.
- **La gobernanza económica de la IA se juega en el diseño de los usos.** Dos arquitecturas que prestan el mismo servicio pueden diferir en un factor de 4 a 8 en consumo: esa elección pertenece a la dirección técnica, aguas arriba — el control de la factura siempre llega demasiado tarde.
- **Entre la prohibición general y la confianza ciega, existe una vía gobernable.** El control humano graduado se especifica, se prueba y se audita; es el enfoque que dibujan las exigencias regulatorias, y es operativo desde ya.
- **Un directivo que practica arbitra mejor.** Hacer o mandar hacer, deuda aceptable o no, promesa de proveedor creíble o no — estas decisiones ganan en acierto cuando se ha probado la materia. Este proyecto es una forma de mantener esa proximidad con el terreno.

*Proyecto personal, llevado a cabo fuera de toda actividad profesional. Cifras procedentes de la auditoría técnica de julio de 2026 — tests ejecutados, mediciones efectuadas sobre el código, hallazgos contraverificados. Repositorio: [github.com/jgouviergmail/LIA-Assistant](https://github.com/jgouviergmail/LIA-Assistant).*

Después el asistente aprendió a mostrar su propio trabajo: una página de Actividad que recoge todo lo que hace por sí mismo, reglas aprendidas que se pueden leer y corregir, una memoria que fecha sus recuerdos y archiva sin borrar, una voz que respira con su ánimo. La autonomía creció exactamente como exigía la filosofía del proyecto: dentro del marco, bajo la mirada del usuario.
