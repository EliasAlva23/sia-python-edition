# Informe de Interfaces — SIA

**Sistema de Asistencia Inteligente — plataforma multi-institución**  
Tech & Innovation Team · Institución inicial: Instituto de Educación Superior N° 11  
Versión del documento: noviembre de 2026 (esquema de datos v4)  

---

## 1. Principios de diseño

| Principio | Cómo se aplica |
|---|---|
| Identidad institucional (marca blanca) | Cada institución tiene nombre, logo, color principal y color secundario propios, y se aplican al login, encabezados, botones, anillos de los indicadores, gráficos de una serie y reportes PDF. Se llega por el enlace `…/?i=identificador`. |
| Paleta base de SIA | Azul marino profundo `#142033` (texto y panel de acceso), azul acero `#2E5772` (acento por defecto), verde azulado `#3F7C70`, verde oliva `#70812B` y fondo claro suave `#EEF0EC`. Se ofrecen como paletas sugeridas: «Acero y marino», «Verde azulado», «Oliva» y «Marino profundo». |
| Sobriedad | Superficies planas, bordes finos de 1 px, esquinas de 14 px, sin degradés ni sombras marcadas. Un solo color de acento por pantalla. |
| Tipografía | Plus Jakarta Sans (400 a 700) desde Google Fonts, con Inter y la fuente del sistema como respaldo si no carga. Títulos en 700, texto con interlineado 1,6 para lectura cómoda. |
| Indicadores circulares | Cada indicador es una tarjeta con un anillo: el arco cubre el porcentaje (o la proporción sobre el total) y el valor va en el centro, con la etiqueta y el contexto debajo. Rojo, ámbar y verde se reservan para estados y siempre van acompañados de texto. |
| Contraste | El texto sobre el color institucional se elige automáticamente (blanco o marino). El panel de acceso lleva el color hacia el marino hasta lograr 7:1 con texto blanco. En modo oscuro el acento se aclara hasta 4,5:1. La configuración de identidad muestra el contraste antes de guardar. |
| Modo claro y oscuro | Claro por defecto; interruptor «Modo oscuro» en la barra lateral. El oscuro usa la misma paleta (fondo `#0D1522`, superficies `#142033`). |
| Cero scroll horizontal | Las tablas pasan a tarjetas en pantallas angostas, los indicadores se ordenan de a dos, las etiquetas largas de los gráficos se parten en renglones y las pestañas se acomodan en varias filas. Verificado en 375 y 1024 px. |
| Lenguaje cotidiano | «Mi historial», «Análisis por reglas de asistencia», mensajes de error que explican qué hacer. |

## 2. Elementos comunes a todas las vistas

- **Encabezado:** logo circular de la institución, nombre de la institución en versalitas, título del panel y bajada, con una línea corta del color institucional debajo.
- **Barra lateral:** marca de la institución, nombre, rol y DNI de la persona, **selector de perfil** (si tiene varios roles o instituciones), interruptor de modo oscuro, cambiar contraseña, cerrar sesión y aviso de expiración (30 minutos sin actividad; recargar la página no cierra la sesión). En celulares se abre con el botón «>>»; el contenido deja espacio arriba para que el botón no tape el encabezado.
- **Indicadores:** grilla de tarjetas circulares (de a dos en celulares).
- **Gráficos:** Plotly con la tipografía de la app, grilla fina, una sola escala, leyenda debajo del gráfico cuando hay varias series y umbrales como línea rotulada.
- **Aviso global:** si la Administración general publica un aviso, aparece arriba de cada panel.
- **Pie de página:** logo y leyenda «SIA · Desarrollado por Tech & Innovation Team».
- **Elementos ocultos:** menú nativo de Streamlit, botones de GitHub, Share y Deploy, insignia «Hosted with Streamlit» y botón «Manage app».

## 3. Pantalla de acceso

| Elemento | Detalle |
|---|---|
| Panel institucional (izquierda) | Fondo marino teñido con el color de la institución, logo circular, «SIA · Sistema de Asistencia Inteligente», nombre de la institución, tres beneficios con viñetas circulares y círculos decorativos de línea fina. En celulares queda arriba del formulario. |
| Institución | Si se entró por `?i=identificador` o el navegador la recuerda (cookie `sia_inst`), ya viene elegida; si hay varias instituciones activas aparece un selector. Toda la pantalla se recolorea con su identidad. |
| Bienvenida | Título «Te damos la bienvenida» y una línea de ayuda. |
| Pestaña Ingresar | DNI o email y contraseña. Bloqueo temporal tras 5 intentos fallidos. Si la persona tiene varios perfiles, elige con cuál entrar. |
| Pestaña Crear cuenta | Estudiante o Docente (según lo habilitado por la Administración general). Orden: Nombre, Apellido, DNI, Email, Legajo o Departamento, Contraseña, Repetir contraseña. El alta docente pide el código de la institución si está definido. |
| Aviso de QR pendiente | Si la persona llegó escaneando un QR, una tarjeta le indica que ingrese o cree su cuenta; al terminar, la inscripción o el presente se registran solos. |

## 4. Panel del Estudiante

Arriba de las pestañas:

- **Alerta de riesgo:** banner rojo automático cuando el porcentaje de una materia queda bajo el umbral (indica cuántas clases seguidas necesita para recuperar la regularidad); banner ámbar cuando acumula faltas seguidas.
- **Indicadores circulares:** asistencia general (anillo con el porcentaje, en rojo, ámbar o verde según el umbral), presentes y ausencias (anillo con la proporción sobre el total de clases; ausencias con la racha actual) y cantidad de materias.

### 4.1 Pestaña "Dar presente"

| Elemento | Detalle |
|---|---|
| Clases abiertas | Etiquetas con las materias que tienen una clase en curso. |
| Escáner en vivo | Se activa con "Activar cámara". Lee el QR proyectado sin sacar foto, con selector de cámara si hay más de una (se recuerda la elección). Usa la cámara trasera en celulares. |
| Alternativa con foto | Desplegable "¿No lee en vivo? Sacá una foto del QR". |
| PIN de 6 dígitos | Formulario para dar presente sin cámara. |
| Resultado | Mensaje verde (presente registrado), azul (ya tenía presente) o rojo (QR vencido, PIN incorrecto, etc.). |

### 4.2 Pestaña "Unirme a una materia"

- Formulario con el código de la materia (`SIA-XXXXXX`).
- Escáner en vivo del QR de inscripción.
- Lista "Mis materias": nombre, curso y comisión, turno, días y horario, estado de la clase de hoy y botón para descargar el **programa en PDF** si el docente lo cargó.

### 4.3 Pestaña "Mi historial"

| Sección | Detalle |
|---|---|
| Porcentaje por materia | Tarjetas con porcentaje, clases asistidas y barra de progreso coloreada según el umbral. |
| Alertas por materia | Aviso si está por debajo del umbral o con faltas seguidas. |
| Mi historial de asistencia | Por materia, cada clase como un ícono con su fecha (presente, tarde, justificado, ausente). Los íconos pasan de línea: no hay tabla ancha. |
| Evolución | Gráfico de la asistencia acumulada por materia con la línea del 75 %. |
| Detalle clase por clase | Tabla responsiva (fecha, materia, estado y hora) y descarga en CSV o Excel. |

### 4.4 Pestaña "Mi credencial"

- QR de la credencial: fijo, firmado digitalmente (no vence y no puede falsificarse cambiando el DNI).
- Datos del estudiante y descarga de la credencial en PNG.

## 5. Panel del Docente

Arriba de las pestañas:

- **Alerta de riesgo:** banner con los alumnos que pueden perder la regularidad en cualquiera de sus materias (los tres primeros y un resumen del resto).
- **Materia activa:** se elige en la barra lateral; las pestañas Clase en vivo, Lector QR e Historial trabajan sobre ella.

### 5.1 Pestaña "Materias"

**Nueva materia / Editar materia** (formulario):

| Campo | Tipo |
|---|---|
| Nombre de la materia | Texto, obligatorio |
| Curso | Selector: 1° a 4° Año |
| Comisión | Selector: Comisión 1 a 6 o Comisión única |
| Turno | Selector: Mañana, Tarde o Noche |
| Días de cursada | Selector múltiple: lunes a sábado |
| Desde / Hasta | Selectores de horario cada 10 minutos (07:00 a 23:50); "Hasta" debe ser posterior a "Desde" |
| Umbral | Control deslizante de 50 % a 100 % |
| Descripción | Texto opcional |
| Programa de la materia | Archivo PDF opcional (hasta 8 MB, se verifica que sea un PDF real) |

**Tarjeta de cada materia:** etiquetas de curso y comisión, turno, días y horario; código de clase; indicadores (alumnos, clases dictadas y alumnos en riesgo); botones Regenerar código, Editar materia y Programa (PDF); QR de inscripción descargable; y el desplegable "Alumnos inscriptos", con el resultado final de cada alumno (en curso, aprobado, reprobado, abandono) y la baja de alumnos.

### 5.2 Pestaña "Clase en vivo"

| Estado | Elementos |
|---|---|
| Sin clase abierta | Tema opcional y botón "Iniciar clase de hoy" (o "Reabrir"); tabla de clases anteriores y descarga del reporte PDF de cualquier clase cerrada. |
| Clase en curso | QR dinámico firmado (rota cada 30 segundos y se actualiza cada 2 segundos), cuenta regresiva y PIN de 6 dígitos; indicadores de presentes y porcentaje en tiempo real; tabla de presentes; registro manual (presente, tarde, justificado) y corrección o anulación. |
| Cierre | Botón "Cerrar clase y generar reporte PDF": cierra el registro y genera el PDF para Preceptoría, con descarga inmediata y envío a Google Drive. |

**Reporte PDF de la clase:** encabezado institucional con logo; materia, curso y comisión, turno, días y horario, fecha, tema y docente; resumen (inscriptos, presentes, tardes, justificados, ausentes, porcentaje); listado alfabético con estado, hora y forma de registro; espacio para firma del docente y recepción de Preceptoría.

### 5.3 Pestaña "Lector QR"

| Modo | Uso |
|---|---|
| Cámara en vivo | Escanea la credencial del alumno mostrándola a la webcam o al celular. Selector de cámara, mensajes de error en español y pausa. La misma credencial no se procesa dos veces seguidas. |
| Foto | Alternativa para navegadores sin escaneo en vivo. |
| Manual / lector USB | DNI o contenido de la credencial (los lectores USB escriben el código y envían Enter). |

A la derecha: total de presentes y la lista de los últimos registros. Debajo del escáner, las últimas cinco lecturas con su resultado.

### 5.4 Pestaña "Historial de asistencia"

| Sección | Detalle |
|---|---|
| Alcance | Materia activa o todas las materias del docente. |
| Indicadores | Alumnos, clases dictadas, asistencia promedio, alumnos en riesgo alto y medio. |
| Historial de asistencia | Una fila por alumno con porcentaje, barra y un ícono por clase con su fecha. |
| Alerta de riesgo (IA) | Mensaje sobre el método usado: "Predicción con IA" (Random Forest, con su precisión medida) o "Análisis por reglas de asistencia" cuando todavía no hay historial suficiente. Tarjetas de los alumnos en riesgo alto, importancia de cada variable y tabla de todos los alumnos con nivel, porcentaje, probabilidad y motivos. |
| Estadísticas | Tendencia semanal, asistencia por día de la semana, mapa de calor y asistencia por alumno según el nivel de riesgo. |
| Exportar reportes | CSV, Excel (hojas Registros, Historial y Riesgo) y envío del Excel a Google Drive. |

## 6. Panel de Preceptoría

| Pestaña | Contenido |
|---|---|
| Registro manual | Materia y fecha; un selector de estado por alumno (presente, tarde, justificado, ausente) y «marcar a todos». Crea la clase si no existe y regenera el PDF si estaba cerrada. |
| Vincular alumno | Busca por DNI e inscribe en una materia; si no tiene cuenta la crea con una contraseña temporal que se muestra una sola vez. |
| Justificativos | Bandeja con aprobación o rechazo en lote, descarga del comprobante y justificación masiva por período y materia. |
| Clases de hoy | Estado de las clases del día y descarga de sus PDF. |
| Consultar alumno | Asistencia y condición de un alumno en todas sus materias. |

## 7. Panel de Rectoría / Dirección

| Pestaña | Contenido |
|---|---|
| Resumen institucional | Período (30 días, 90 días o todo el ciclo); indicadores de asistencia, promoción, regularidad, libres y riesgo; asistencia por carrera, condición por carrera (barras 100 %), tendencia semanal con la línea de regularidad, materias con menor asistencia, detalle por materia, alumnos en riesgo alto y reporte institucional. |
| Carreras y materias | Alta y edición de carreras y asignación de carreras a cada docente. |
| Personal | Personal con su rol; asignar rol por DNI (o crear la cuenta con contraseña temporal) y quitar roles. |
| Configuración | Umbrales de regularidad y promoción, tolerancia de llegada tarde, código de alta docente, nombre, colores y logo (con vista previa y control de contraste). |

## 8. Administración general

| Pestaña | Contenido |
|---|---|
| Instituciones | Listado con enlace de acceso y cantidades; alta de institución (con persona a cargo de Dirección); edición de identidad y configuración; suspensión o reactivación. |
| Usuarios y roles | Búsqueda por DNI, roles en todas las instituciones, asignar o quitar roles y cerrar sesiones. |
| Sistema | Funciones habilitadas (registro, autoinscripción, IA, justificativos), aviso global y estado de la base. |

## 9. Comportamiento en celulares

- Las columnas se apilan, los indicadores pasan a dos por fila y las tablas se muestran como tarjetas.
- Las pestañas se acomodan en varias filas, sin desplazamiento lateral.
- La barra lateral se abre con el botón ">>".
- La app se puede instalar en la pantalla de inicio (Android: "Instalar app"; iPhone: Safari, Compartir, "Agregar a inicio").
