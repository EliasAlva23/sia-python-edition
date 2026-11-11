# Informe de Interfaces — SIA · IES N° 11

**Sistema de Asistencia Inteligente (Python Edition)**  
Instituto de Educación Superior N° 11 · Desarrollado por Tech & Innovation Team  
Versión del documento: noviembre de 2026  

---

## 1. Principios de diseño

| Principio | Cómo se aplica |
|---|---|
| Identidad institucional | Paleta del IES N° 11: lila `#B78FB6` (acentos), lavanda `#7979B1` (secundarios), azul `#346FB0` (botones y bordes), azul oscuro `#02447B` (tarjetas en modo oscuro) y azul noche `#003467` (fondo en modo oscuro). Tipografía Plus Jakarta Sans. |
| Modo claro y oscuro | Interruptor "Modo oscuro" en la barra lateral. Tablas, gráficos, cámara y alertas se adaptan a cada modo. |
| Cero scroll horizontal | Ninguna vista se desplaza de costado: las tablas se transforman en tarjetas en pantallas angostas, el historial usa íconos que pasan de línea y las pestañas se acomodan en varias filas. Verificado en 1280, 375 y 320 px. |
| Lenguaje cotidiano | "Mi historial" en lugar de "sábana"; "Análisis por reglas de asistencia" en lugar de "modo heurístico"; mensajes de error que explican qué hacer. |
| Accesible desde el celular | Instalable como app (PWA), escáner con cámara trasera, PIN de 6 dígitos como alternativa a la cámara. |

## 2. Elementos comunes a todas las vistas

- **Encabezado (banner):** logo circular del IES N° 11, saludo y descripción del panel.
- **Barra lateral:** marca "SIA · IES N° 11", interruptor de modo oscuro, tarjeta del usuario (nombre, DNI y rol), cambiar contraseña, cerrar sesión y aviso de expiración de la sesión (30 minutos sin actividad). En el docente incluye además el selector de **materia activa**. En celulares se abre con el botón ">>" de la esquina superior izquierda.
- **Pie de página:** logo y leyenda "Desarrollado por Tech & Innovation Team — IES N° 11".
- **Elementos ocultos:** menú nativo de Streamlit, botones de GitHub, Share y Deploy, insignia "Hosted with Streamlit" y botón "Manage app" de Streamlit Cloud.

## 3. Pantalla de acceso

| Elemento | Detalle |
|---|---|
| Pestaña Ingresar | DNI o email y contraseña. Validación de campos vacíos y bloqueo temporal tras 5 intentos fallidos. |
| Pestaña Crear cuenta | Tipo de cuenta (Estudiante / Docente). Orden de campos: Nombre, Apellido, DNI, Email, Legajo o Departamento, Contraseña, Repetir contraseña. Todos los errores se muestran juntos. Si está configurado `SIA_DOCENTE_CODE`, el alta docente pide el código institucional. |
| Aviso de QR pendiente | Si la persona llegó escaneando un QR con la cámara del celular, una tarjeta le indica que ingrese o cree su cuenta; al terminar, la inscripción o el presente se registran solos. |

## 4. Panel del Estudiante

Arriba de las pestañas:

- **Alerta de riesgo:** banner rojo automático cuando el porcentaje de una materia queda bajo el umbral (indica cuántas clases seguidas necesita para recuperar la regularidad); banner ámbar cuando acumula faltas seguidas.
- **Indicadores:** asistencia general, presentes, ausencias (con racha actual) y cantidad de materias.

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
| Desde / Hasta | Selectores de horario cada 30 minutos (07:00 a 23:30); "Hasta" debe ser posterior a "Desde" |
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

## 6. Comportamiento en celulares

- Las columnas se apilan, los indicadores pasan a dos por fila y las tablas se muestran como tarjetas.
- Las pestañas se acomodan en varias filas, sin desplazamiento lateral.
- La barra lateral se abre con el botón ">>".
- La app se puede instalar en la pantalla de inicio (Android: "Instalar app"; iPhone: Safari, Compartir, "Agregar a inicio").
