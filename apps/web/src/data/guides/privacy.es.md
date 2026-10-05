# LIA — Política de privacidad

> Tus datos. Tu asistente. Tus reglas.

**Versión**: 1.0
**Fecha**: 2026-10-05
**Licencia**: AGPL-3.0 (código abierto)

---

## Índice

1. [Introducción](#introduction)
2. [Datos recopilados](#data_collected)
3. [Bases jurídicas del tratamiento](#legal_basis)
4. [Alojamiento y ubicación de los datos](#hosting)
5. [Seguridad de los datos](#security)
6. [Proveedores de LLM](#llm_providers)
7. [Conservación de los datos](#retention)
8. [Tus derechos](#rights)
9. [Cookies](#cookies)
10. [Contacto](#contact)

---

## 1. Introducción

Esta política de privacidad describe cómo LIA, un asistente personal de IA de código abierto, recopila, utiliza y protege tus datos personales. LIA es desarrollado y operado por un desarrollador independiente como proyecto de código abierto bajo la licencia AGPL-3.0.

LIA se encuentra actualmente en fase beta y se ofrece de forma gratuita durante este período. La aplicación está disponible en [https://lia.jeyswork.com](https://lia.jeyswork.com). El código fuente completo es público, lo que te permite auditar en cualquier momento cómo se tratan tus datos.

Esta política se aplica a la instancia alojada de LIA. Si despliegas tu propia instancia (autoalojamiento), controlas su funcionamiento y debes evaluar las obligaciones de protección de datos aplicables a tu uso; esta política no se aplica directamente. Aun así, te animamos a utilizarla como punto de partida para esa evaluación.

Al utilizar LIA, reconoces que has leído y comprendido esta política. Si no aceptas las condiciones aquí descritas, no utilices el servicio.

## 2. Datos recopilados

LIA trata las siguientes categorías de datos para prestar el servicio y las funciones opcionales que elijas utilizar:

**Datos de la cuenta de usuario:**
- Dirección de correo electrónico (identificador único)
- Nombre y apellidos
- Contraseña (con hash mediante bcrypt, nunca almacenada en texto claro)
- Preferencias de idioma y zona horaria
- Rol del usuario (estándar o administrador)

**Datos de las conversaciones:**
- Mensajes intercambiados entre tú y el asistente
- Planes de ejecución generados por el sistema de planificación
- Resultados de las acciones realizadas por los agentes (búsqueda de correos, creación de eventos, etc.)
- Historial de conversaciones, guardado como checkpoints en PostgreSQL
- Recuerdos, preferencias, documentos y otros contenidos que proporcionas para personalizar el asistente

**Datos de conexión a servicios de terceros:**
- Tokens de acceso y de renovación OAuth para los servicios que utilizan OAuth, incluidos Google Workspace y Microsoft 365
- Contraseñas específicas de aplicación u otras credenciales para conectores como Apple iCloud, y claves API de proveedores que configures
- Estos secretos almacenados se cifran con Fernet (AES-128-CBC con autenticación HMAC-SHA256)

**Datos de funciones opcionales:**
- Una dirección de domicilio que guardes y la ubicación del navegador si das permiso; recordar la última posición conocida también requiere una activación voluntaria. Estos campos de ubicación están cifrados, la posición recordada sustituye a la anterior sin crear un historial de ubicaciones, y desactivar la opción la borra
- Audio, transcripciones y las imágenes o documentos utilizados en una solicitud de voz, una reunión o una solicitud multimodal
- Mediciones de salud si eliges conectar una fuente y utilizar las funciones de salud

**Datos de uso:**
- Métricas operativas agregadas (número de solicitudes, tiempos de respuesta) y registros de uso por cuenta
- Contadores de tokens LLM consumidos por sesión
- Registros de errores técnicos con controles para ocultar secretos y contenido personal; las trazas de diagnóstico opcionales tienen un alcance independiente, descrito más adelante

**Datos que LIA NO recopila:**
- Plantillas de autenticación biométrica que conserva tu dispositivo cuando utilizas una clave de acceso (passkey)
- Datos de navegación fuera de la aplicación
- Perfiles publicitarios o datos de segmentación

## 3. Bases jurídicas del tratamiento

La siguiente tabla identifica las bases jurídicas utilizadas para el servicio alojado conforme al Reglamento General de Protección de Datos (RGPD):

| Actividad de tratamiento | Base jurídica | Justificación |
|---|---|---|
| Creación y gestión de la cuenta | Ejecución de un contrato (art. 6.1.b) | Necesaria para prestar el servicio |
| Conversaciones con el asistente | Ejecución de un contrato (art. 6.1.b) | Función principal del servicio |
| Conexiones a servicios de terceros (Google, Apple, Microsoft) | Consentimiento explícito (art. 6.1.a) | Eliges activamente conectar cada servicio |
| Envío de datos a proveedores de LLM | Ejecución de un contrato (art. 6.1.b) | Necesario para que el asistente funcione |
| Registros técnicos y métricas | Interés legítimo (art. 6.1.f) | Mantener la seguridad y la fiabilidad del servicio |
| Cookie de preferencia de idioma | Consentimiento (art. 6.1.a) | Guardar tu elección de idioma |

Puedes retirar tu consentimiento en cualquier momento para los tratamientos basados en él, sin afectar a la licitud del tratamiento realizado antes de su retirada.

## 4. Alojamiento y ubicación de los datos

**Infraestructura de la instancia alojada:**

La instancia oficial de LIA se autoaloja en un servidor físico administrado por el desarrollador. Los datos se almacenan en Francia.

- **Base de datos**: PostgreSQL para el almacenamiento persistente (cuentas, conversaciones, checkpoints)
- **Caché**: Redis para las sesiones y la caché temporal
- **Proxy inverso**: Cloudflare Tunnel para el acceso HTTPS seguro
- **Certificados TLS**: Gestionados automáticamente por Cloudflare

**Transferencias internacionales de datos:**

Cuando interactúas con LIA, los datos necesarios para tu solicitud pueden transmitirse a proveedores de modelos, voz, avatares, búsqueda u otros servicios, según las funciones y la configuración que utilices. Estos proveedores pueden tener servidores fuera de la Unión Europea, especialmente en Estados Unidos y China. Consulta la sección «Proveedores de LLM» para obtener más información.

Las conexiones a Google Workspace, Apple iCloud y Microsoft 365 también implican intercambios con los servidores de estos proveedores, sujetos a sus propias políticas de privacidad.

## 5. Seguridad de los datos

LIA implementa una arquitectura de seguridad de varias capas diseñada para proteger tus datos en cada etapa:

**Arquitectura BFF (Backend-for-Frontend):**
La sesión de la aplicación utiliza una cookie HttpOnly, y las credenciales de larga duración de los conectores y los secretos API de modelos o avatares se gestionan en el servidor. Algunas conexiones de voz y avatares utilizan credenciales de sesión temporales en el navegador. Google Maps interactivo también recibe una clave API para navegador tras una activación autenticada; esa clave requiere restricciones en el proveedor y cuotas adecuadas.

**Cifrado de datos sensibles:**
- Las credenciales de conectores, los secretos de proveedores y los campos de ubicación designados que se almacenan se cifran con [Fernet](https://cryptography.io/en/latest/fernet/) (AES-128-CBC + autenticación HMAC-SHA256)
- Las contraseñas se protegen con hash mediante bcrypt (factor de coste adaptativo)
- El acceso a la aplicación alojada utiliza HTTPS; la protección de las conexiones internas y las copias de seguridad depende del despliegue

Este cifrado por campos no cifra todas las columnas de la base de datos. El servidor puede leer las conversaciones para procesarlas y estas no están cifradas de extremo a extremo. Un operador con acceso a la base de datos y a la clave de cifrado puede acceder a los datos almacenados; la seguridad de ese acceso y de las copias de seguridad también depende de la operación de la instancia.

**Información personal y diagnósticos:**
Los controles de ocultación protegen los registros técnicos; no anonimizan automáticamente el contexto enviado a un modelo. Tus mensajes y el contenido relevante de los servicios conectados pueden contener información personal necesaria para tu solicitud. Si se activa el seguimiento de LLM, las herramientas de diagnóstico también pueden conservar entradas, salidas del modelo y metadatos vinculados a la cuenta. El operador debe configurar su acceso, alojamiento y conservación.

**Sesiones y autenticación:**
- Las sesiones de usuario se almacenan en Redis con caducidad automática
- La autenticación se basa en cookies seguras (HttpOnly, Secure, SameSite)
- El JavaScript del cliente no puede leer la cookie HttpOnly de sesión de la aplicación; las credenciales temporales de las sesiones de voz o avatares activadas en el navegador tienen un propósito distinto

**Registros seguros:**
Los registros técnicos utilizan un formato JSON estructurado (mediante structlog), con reglas para omitir contenido citado del usuario y ocultar secretos e información personal reconocidos. Estos controles no convierten todos los almacenes de diagnóstico en anónimos.

## 6. Proveedores de LLM

LIA utiliza varios proveedores de grandes modelos de lenguaje (LLM) para procesar tus solicitudes. La elección depende de la configuración de tu instancia y del tipo de tarea:

| Proveedor | Sede | Uso en LIA |
|---|---|---|
| OpenAI | Estados Unidos | Modelos GPT para conversación y planificación |
| Anthropic | Estados Unidos | Modelos Claude para conversación y análisis |
| Google (Gemini) | Estados Unidos | Modelos Gemini para procesamiento multimodal |
| DeepSeek | China | Modelos de razonamiento avanzado |
| Qwen (Alibaba) | China | Modelos de procesamiento del lenguaje |
| Perplexity | Estados Unidos | Búsqueda web ampliada |
| Ollama | Depende del endpoint configurado | Inferencia de modelos en un servidor local cuando se configura así |

**Qué se transmite a los proveedores de LLM:**
- El contenido de tus mensajes
- El contexto conversacional necesario para la coherencia de las respuestas
- Los resultados relevantes de las herramientas (contenido de correos, detalles de eventos, documentos, etc.), que pueden contener datos personales

Los flujos de voz, reuniones, imágenes y del avatar parlante opcional también pueden transmitir el audio, texto o imágenes que necesitan sus respectivos proveedores. Las funciones seleccionadas y el enrutamiento determinan qué servicios los reciben.

**Cómo se utilizan las credenciales:**
Las credenciales de los conectores y las claves de proveedores se utilizan para autenticarse ante el servicio correspondiente; no se añaden a los prompts de los modelos como contenido de la conversación. Evita incluir contraseñas u otros secretos en tus mensajes: el contenido que aportas puede formar parte de una solicitud a un proveedor.

**Compromisos de los proveedores:**
El uso para entrenamiento, la conservación y otras formas de tratamiento de los datos dependen del proveedor, el producto, la configuración de la cuenta y el contrato o la política de privacidad aplicables. Revisa esas condiciones para cada servicio que actives; LIA no puede ofrecer en su nombre una garantía universal de que los datos no se utilicen para entrenamiento.

Elegir un endpoint de Ollama alojado localmente mantiene la inferencia del modelo seleccionado en ese endpoint. Esto no convierte en locales las demás integraciones: las cuentas conectadas, la búsqueda web y los servicios remotos de voz o avatares pueden seguir intercambiando datos con sus proveedores.

## 7. Conservación de los datos

Los períodos de conservación se definen según la naturaleza de los datos:

| Tipo de datos | Período de conservación | Justificación |
|---|---|---|
| Cuenta de usuario | El contenido personal se purga en la fase de eliminación; el registro de la cuenta y los registros de facturación permanecen hasta la fase de borrado o el vencimiento de conservación que les corresponda | Operación del servicio, contabilidad y obligaciones legales aplicables |
| Historial de conversaciones | Hasta su eliminación por el usuario o la eliminación de la cuenta | Continuidad del servicio |
| Credenciales cifradas de los conectores | Hasta la desconexión del servicio o la eliminación de la cuenta | Acceso a los servicios conectados |
| Ubicación del navegador recordada | Se sustituye al actualizarse y se borra cuando se desactiva su almacenamiento voluntario; su vigencia limita su uso | Solicitudes basadas en ubicación sin historial de ubicaciones |
| Sesiones Redis | Caducidad automática según los ajustes de sesión y de «Recordarme» | Seguridad |
| Registros técnicos y trazas de diagnóstico opcionales | Conservación configurada para cada almacén de diagnóstico | Diagnóstico y seguridad |
| Métricas de uso | Conservación configurada para el almacén de métricas; los registros vinculados a la cuenta siguen su ciclo de vida documentado | Contabilidad del uso y operación del servicio |

**Eliminación de la cuenta:**
Puedes solicitar la eliminación de la cuenta al administrador. La fase de eliminación purga contenidos personales como conversaciones, recuerdos, documentos, checkpoints y credenciales de conectores almacenadas, pero conserva el registro de la cuenta, incluidos el nombre y el correo electrónico, y los registros de facturación. La fase posterior de borrado definitivo retira el registro restante de la cuenta. Los registros de auditoría, los almacenes de diagnóstico separados, las copias de seguridad y los datos que ya hayan recibido los proveedores requieren sus propios procedimientos de conservación y borrado; ninguna de estas fases borra todas las copias de inmediato. El operador debe gestionar las solicitudes de supresión aplicables en todos esos almacenes.

## 8. Tus derechos

Conforme al RGPD, tienes los siguientes derechos:

- **Derecho de acceso** (art. 15): Obtener una copia de todos los datos personales que conservamos sobre ti.
- **Derecho de rectificación** (art. 16): Corregir datos personales inexactos o incompletos.
- **Derecho de supresión** (art. 17): Solicitar la eliminación de tus datos personales («derecho al olvido»).
- **Derecho a la limitación** (art. 18): Solicitar la limitación del tratamiento de tus datos en determinadas circunstancias.
- **Derecho a la portabilidad de los datos** (art. 20): Recibir tus datos en un formato estructurado, de uso común y legible por máquina.
- **Derecho de oposición** (art. 21): Oponerte al tratamiento de tus datos basado en el interés legítimo.
- **Derecho a retirar el consentimiento**: En cualquier momento, sin afectar a la licitud del tratamiento realizado antes de su retirada.

Para ejercer estos derechos, contacta con nosotros en la dirección indicada en la sección «Contacto». Responderemos sin dilación indebida y, normalmente, en el plazo de un mes desde la recepción de tu solicitud; cualquier prórroga justificada se comunicará conforme al [artículo 12 del RGPD](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng).

Si consideras que no se respetan tus derechos, tienes derecho a presentar una reclamación ante la CNIL (Commission Nationale de l'Informatique et des Libertés) o cualquier otra autoridad de control competente.

## 9. Cookies

LIA utiliza un número mínimo de cookies, exclusivamente funcionales:

| Cookie | Finalidad | Duración | Tipo |
|---|---|---|---|
| `NEXT_LOCALE` | Guarda tu preferencia de idioma (fr, en, de, es, it, zh) | 1 año | Funcional |
| Cookie de sesión | Mantiene tu sesión de autenticación | Duración de la sesión | Estrictamente necesaria |

**Lo que LIA NO utiliza:**
- No utiliza cookies de seguimiento
- No utiliza cookies publicitarias
- No utiliza cookies de analítica de terceros (Google Analytics, etc.)
- No utiliza píxeles de seguimiento
- No utiliza fingerprinting del navegador

Las cookies utilizadas por LIA son estrictamente necesarias para el funcionamiento del servicio o están relacionadas con tu elección explícita (preferencia de idioma). Conforme a la Directiva ePrivacy, las cookies estrictamente necesarias no requieren consentimiento previo.

## 10. Contacto

Para cualquier pregunta sobre la protección de tus datos personales, el ejercicio de tus derechos o esta política, puedes contactar con nosotros:

- **Correo electrónico**: liamyassistant@gmail.com
- **Sitio web**: [https://lia.jeyswork.com](https://lia.jeyswork.com)
- **Código fuente**: [GitHub](https://github.com/jgouviergmail/LIA-Assistant) (AGPL-3.0)

**Responsable del tratamiento:**
LIA es operado por un desarrollador independiente que actúa como responsable del tratamiento en el sentido del RGPD.

**Cambios en esta política:**
Esta política puede actualizarse para reflejar cambios en el servicio o en la normativa aplicable. En caso de una modificación sustancial, recibirás una notificación a través de la aplicación. Prevalece la fecha de actualización que figura al principio de este documento. Te animamos a revisar esta política regularmente.

**Transparencia del código abierto:**
Como proyecto de código abierto, LIA te permite auditar el código fuente en cualquier momento para verificar exactamente qué datos se recopilan, cómo se tratan y a dónde se envían. Esta transparencia radical es un compromiso fundamental del proyecto.
