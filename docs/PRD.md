# PRD — Documento de Requisitos del Producto

**SIA · Sistema de Asistencia Inteligente — IES N° 11**  
Instituto de Educación Superior N° 11 · Tech & Innovation Team  
Versión: noviembre de 2026 · Estado: en producción (Streamlit Community Cloud)  

---

## 1. Resumen

SIA registra la asistencia de las clases del IES N° 11 con códigos QR firmados, muestra a docentes y estudiantes su historial de asistencia y alerta de forma temprana cuando un alumno puede perder la regularidad, combinando reglas de asistencia con un modelo de aprendizaje automático.

## 2. Problema

- La asistencia en papel es lenta, se pierde y no permite ver tendencias a tiempo.
- Los alumnos no saben cuántas faltas les quedan antes de quedar libres.
- Preceptoría necesita un comprobante formal por clase.
- La información se comparte por canales dispersos (planillas sueltas, mensajes).

## 3. Objetivos

| Objetivo | Indicador de éxito |
|---|---|
| Tomar asistencia en menos de 2 minutos por curso | Presentes registrados por QR o PIN desde el inicio de la clase |
| Detectar riesgo de pérdida de regularidad antes del cierre del cuatrimestre | Alumnos alertados con al menos 3 clases de margen para recuperar |
| Entregar a Preceptoría un comprobante por clase | PDF generado en el 100 % de las clases cerradas |
| Usable desde cualquier celular o computadora | Cero scroll horizontal; escáner funcionando en webcams de PC y en smartphones |

## 4. Usuarios

| Rol | Necesidades principales |
|---|---|
| Docente | Crear materias, abrir y cerrar clases, registrar asistencia rápido, ver quién está en riesgo, exportar reportes. |
| Estudiante | Dar presente en segundos, unirse a materias, conocer su situación y su historial, descargar el programa. |
| Preceptoría (destinataria) | Recibir el reporte PDF de cada clase y planillas consolidadas (Excel o Google Drive). |

## 5. Requisitos funcionales

### 5.1 Cuentas y sesión

| ID | Requisito |
|---|---|
| RF-01 | Registro de estudiantes y docentes con validación de nombre, apellido, DNI, email y contraseña (mínimo 8 caracteres con letras y números). |
| RF-02 | El alta docente puede exigir un código institucional (`SIA_DOCENTE_CODE`). |
| RF-03 | Inicio de sesión con DNI o email; bloqueo de 15 minutos tras 5 intentos fallidos. |
| RF-04 | La sesión expira tras 30 minutos sin actividad y a las 8 horas como máximo. |

### 5.2 Materias

| ID | Requisito |
|---|---|
| RF-10 | Crear y editar materias con nombre, curso, comisión, turno, días, horario de inicio y fin, umbral de regularidad y descripción opcional. Curso, comisión, turno, días y horarios se eligen de listas (no hay texto libre). |
| RF-11 | Adjuntar, reemplazar o quitar el programa de la materia en PDF (máximo 8 MB, se verifica que sea un PDF real). Los estudiantes inscriptos lo pueden descargar. |
| RF-12 | Código de inscripción `SIA-XXXXXX` y QR firmado; el docente puede regenerarlo para invalidar el anterior. |
| RF-13 | Cargar el resultado final de cada alumno (aprobado, reprobado, abandono); alimenta el modelo de IA. |
| RF-14 | Archivar materias y dar de baja alumnos. |

### 5.3 Asistencia

| ID | Requisito |
|---|---|
| RF-20 | Abrir la clase del día (con tema opcional); una clase por materia y por fecha. |
| RF-21 | QR dinámico firmado con `SIA_SECRET` que rota cada 30 segundos; se acepta también el inmediatamente anterior. PIN de 6 dígitos equivalente. |
| RF-22 | Con la app publicada, el QR es un enlace: la cámara nativa del celular abre la app y, tras ingresar o crear la cuenta, el presente se registra sin volver a escanear (hasta 10 minutos). |
| RF-23 | Si quien escanea el QR de asistencia no estaba inscripto, se lo inscribe y se registra su presente en el mismo paso. |
| RF-24 | El docente escanea la credencial QR fija y firmada del alumno (`SIA:STUDENT:<dni>:<firma>`), o ingresa el DNI a mano o con un lector USB. |
| RF-25 | Escáner en vivo con selector de cámara (MediaDevices), cámara trasera preferida en celulares, decodificación nativa o jsQR, mensajes de error en español y foto como alternativa. |
| RF-26 | Idempotencia: un alumno tiene como máximo un registro por clase; las lecturas repetidas informan "ya tenía presente". |
| RF-27 | Registro manual con estado presente, tarde o justificado; corrección y anulación. |
| RF-28 | Al cerrar la clase se genera automáticamente un reporte PDF para Preceptoría, descargable y enviable a Google Drive; queda guardado y se puede volver a descargar desde el historial de clases. |

### 5.4 Historial, alertas y reportes

| ID | Requisito |
|---|---|
| RF-30 | "Mi historial" del estudiante: porcentaje por materia, íconos por clase, evolución y detalle exportable a CSV o Excel. |
| RF-31 | Historial de asistencia del docente por materia o de todas sus materias, con estadísticas (tendencia semanal, día de la semana, mapa de calor, ranking). |
| RF-32 | Alerta de riesgo automática en ambos paneles: banner rojo cuando un alumno queda bajo el umbral, acumula 3 o más faltas consecutivas o el modelo estima una probabilidad de riesgo de 60 % o más; aviso ámbar al estudiante cuando lleva 2 o más faltas seguidas. |
| RF-33 | El estudiante ve cuántas clases seguidas necesita para recuperar la regularidad. |
| RF-34 | Exportación del historial a CSV y Excel (hojas Registros, Historial y Riesgo) y envío a una carpeta institucional de Google Drive. |

## 6. Inteligencia artificial

- **Modelo:** Random Forest (scikit-learn, 300 árboles, profundidad máxima 6, clases balanceadas).
- **Variables:** porcentaje de asistencia, máximo de faltas consecutivas, faltas en las últimas 4 clases, tendencia (segunda mitad del período menos la primera), racha actual de faltas y cantidad de clases.
- **Entrenamiento:** instantáneas parciales del historial de cada alumno, etiquetadas con el resultado final cargado por el docente o, si no existe, con el desenlace de la asistencia. Validación cruzada agrupada por alumno (AUC).
- **Análisis por reglas de asistencia:** si hay menos de 30 instantáneas o todos los alumnos tienen el mismo desenlace, el riesgo se calcula con reglas transparentes (porcentaje, faltas seguidas y últimas clases) y la interfaz lo informa con ese nombre.
- **Niveles:** ALTO (bajo el umbral, 3 o más faltas consecutivas o probabilidad de 60 % o más), MEDIO y BAJO, con los motivos en lenguaje claro.

## 7. Requisitos no funcionales

| ID | Requisito |
|---|---|
| RNF-01 | Diseño responsivo sin scroll horizontal en ninguna vista (verificado en 320, 375 y 1280 px). |
| RNF-02 | Modo claro y oscuro con contraste legible. |
| RNF-03 | Contraseñas con PBKDF2-HMAC-SHA256, 200 000 iteraciones y sal por usuario; comparación en tiempo constante. |
| RNF-04 | QR y credenciales firmados con HMAC-SHA256 (`SIA_SECRET`). |
| RNF-05 | Instalable como PWA (manifiesto, íconos y metaetiquetas para Android e iOS). |
| RNF-06 | Funciona en Streamlit Community Cloud; sin servidores adicionales. |
| RNF-07 | Google Drive con permiso mínimo `drive.file` (la app solo accede a los archivos que crea). |
| RNF-08 | Textos en español rioplatense y nombre institucional unificado ("IES N° 11"). |

## 8. Pila tecnológica

| Capa | Tecnología |
|---|---|
| Interfaz | Streamlit 1.67 (componentes v2 para el escáner), CSS propio, Plotly |
| Lógica | Python 3.11, programación orientada a objetos |
| Datos | SQLite (`sqlite3`), pandas |
| IA | scikit-learn |
| QR | qrcode, OpenCV, pyzbar (servidor); BarcodeDetector o jsQR (navegador) |
| Reportes | fpdf2 (PDF), openpyxl (Excel) |
| Integraciones | Google Drive API v3 con google-auth |

## 9. Limitaciones conocidas y riesgos

| Tema | Detalle y mitigación |
|---|---|
| Persistencia en Streamlit Cloud | El disco del contenedor es efímero: `database.db` se pierde en reinicios o redespliegues. Mitigación: copias periódicas o servidor con disco persistente (`SIA_DB_PATH`). |
| Google Drive | Requiere credenciales que configura la institución. Con cuenta de servicio, la carpeta debe estar en una Unidad compartida (las cuentas de servicio no tienen espacio propio). |
| Elementos de Streamlit Cloud | El ocultamiento de "Manage app" y de la insignia depende de la estructura actual de Cloud; si Streamlit la cambia, hay que actualizar los selectores. |
| Escáner | Requiere https y permiso de cámara; si el navegador lo bloquea, quedan la foto, el PIN y el ingreso manual. |
| Precisión de la IA | Sin resultados finales cargados, las etiquetas se derivan de la propia asistencia y la precisión informada es optimista. |

## 10. Fuera de alcance (por ahora)

- Integración con el sistema de gestión académica del Ministerio.
- Notificaciones por email o WhatsApp.
- Múltiples instituciones en una misma instalación.
