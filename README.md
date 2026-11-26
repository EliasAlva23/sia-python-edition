# SIA — Sistema de Asistencia Inteligente

Plataforma **SaaS multi-institución** en **Streamlit** para gestionar la asistencia en institutos de nivel superior:
asistencia por QR o PIN, registro manual de Preceptoría, justificativos, condición académica
(promoción / regularidad / libre) con umbrales configurables, reportes PDF/Excel y predicción de riesgo
con **Random Forest** (`scikit-learn`).

## Instituciones y roles

- **Marca blanca:** cada institución tiene nombre, logo y colores propios. Se accede por su enlace
  (`…/?i=identificador`), que queda recordado en el navegador; si hay varias, el login muestra un selector.
- **Una cuenta por persona** (DNI único) con roles por institución. Quien tiene varios perfiles los cambia
  desde la barra lateral sin volver a ingresar.

| Perfil | Qué hace |
|---|---|
| Estudiante | Da el presente (QR/PIN), se une a materias, ve su historial y condición, presenta justificativos |
| Docente | Materias por carrera, clase en vivo, lector QR, estadísticas, riesgo IA, revisa justificativos |
| Preceptoría | Registro manual (alumnos sin dispositivo, días anteriores), vincula alumnos, justificación masiva, clases del día |
| Rectoría / Dirección | Resumen ejecutivo por carrera y materia, condición de cursadas, reporte institucional, carreras, personal, umbrales e identidad visual |
| Administración general | Alta y edición de instituciones, roles de cualquier persona, funciones habilitadas, aviso global |

La **Administración general** se otorga solo por Secrets (`SIA_SUPERADMINS = "dni1,dni2"`), nunca desde la app.

**Sesiones persistentes:** al ingresar se guarda una cookie con un token aleatorio (en la base solo se guarda su
hash SHA-256). Recargar la página no cierra la sesión; expira tras `SIA_SESSION_MINUTES` sin actividad
(30 por defecto) o 12 horas como máximo, y cambiar la contraseña cierra todas las sesiones abiertas.

## Documentación

En [`docs/`](docs/) están los informes oficiales, en Markdown y PDF:

| Documento | Contenido |
|---|---|
| [Informe de Interfaces](docs/INFORME_INTERFACES.md) | Detalle de cada vista de los paneles de Alumno y Docente |
| [PRD](docs/PRD.md) | Requisitos funcionales y técnicos del sistema |
| [Arquitectura](docs/ARQUITECTURA.md) | Estructura de carpetas y archivos, modelo de datos, configuración y despliegue |

Los PDF se regeneran con `python docs/generar_pdfs.py` (requiere `pip install markdown fpdf2`).

## Estructura

```
app.py              punto de entrada: página, sesión persistente y ruteo por perfil
core/               base de datos, seguridad, validaciones, fechas, reportes PDF/Excel, Google Drive
models/             Persona (y roles), Institucion, Materia, RegistroAsistencia, Justificativo, PredictorRiesgoIA
utils/qr.py         generación y lectura de códigos QR
views/              paneles por rol, configuración institucional, gráficos, escáner QR, PWA y estilos
scripts/            autorización de Google Drive (se ejecuta una vez)
docs/               informes del sistema (.md y .pdf)
```

## Identidad visual

- Paleta base: azul marino profundo `#142033`, azul acero `#2E5772`, verde azulado `#3F7C70`, verde oliva `#70812B`
  y fondo claro suave `#EEF0EC`, ofrecida como paletas sugeridas al configurar cada institución.
- Diseño sobrio: superficies planas, bordes finos, sin degradés; claro por defecto.
- **Indicadores en tarjetas circulares** (anillo proporcional al dato) en todos los paneles.
- Tipografía Plus Jakarta Sans, con Inter y la fuente del sistema como respaldo.
- El color principal y el logo vienen de la institución activa (los configura Dirección o la Administración
  general, con control de contraste). En modo oscuro el acento se aclara automáticamente hasta 4.5:1.
- Gráficos: una serie usa el color institucional; varias series, una paleta categórica fija; los estados
  (bueno / advertencia / crítico) siempre llevan texto, y los umbrales se dibujan como línea rotulada.
- **Modo claro / oscuro:** interruptor en la barra lateral.

## Instalación en el celular (PWA)

La app agrega el manifiesto (`static/manifest.json`), los íconos y las etiquetas `<meta>` necesarias para
"Agregar a pantalla principal" en Android (Chrome) e iOS (Safari → Compartir → Agregar a inicio).
Requiere `server.enableStaticServing = true` en `.streamlit/config.toml` (ya configurado).

## Materias

Cada materia se carga con selectores: **Curso** (1° a 4° Año), **Comisión**, **Turno** (Mañana / Tarde / Noche),
**Días de cursada**, horario **Desde / Hasta** (cada 10 minutos), **carrera** y umbrales de regularidad y promoción, más una descripción opcional y el **programa en PDF** (hasta 8 MB),
que los alumnos inscriptos pueden descargar. Las bases de versiones anteriores se migran solas al iniciar.

## Escáner QR en vivo

Docentes y alumnos escanean con la cámara **en vivo, sin sacar foto**, desde una webcam de PC o un celular:
selector de cámara (se recuerda la elección), cámara trasera en celulares, decodificación nativa (`BarcodeDetector`)
o jsQR en navegadores que no la traen (Chrome/Edge en Windows) y mensajes de error en español (permiso denegado,
cámara ocupada por otra app, sin cámara). Quedan como alternativas la foto, el PIN y el ingreso manual o lector USB.

## Cierre de clase y reportes

- **Cerrar clase** genera automáticamente el **reporte PDF para Preceptoría** (resumen, listado y firmas); se
  descarga al instante y queda guardado en el historial de clases.
- **Historial de asistencia** (docente) y **Mi historial** (alumno) se exportan a CSV y Excel.
- **Google Drive:** los reportes se pueden enviar a una carpeta institucional. Se configura en Secrets
  (ver la plantilla `.streamlit/secrets.toml.example` y la sección Google Drive de `docs/ARQUITECTURA.md`).
  Sin configurar, el botón aparece deshabilitado.

## Alertas de riesgo

Ambos paneles muestran automáticamente una alerta cuando un alumno puede perder la regularidad (bajo el umbral,
faltas consecutivas o probabilidad de riesgo alta).

## QR con enlace real

Si la app tiene URL pública (`SIA_PUBLIC_URL` en Secrets, o detectada del navegador cuando no es localhost),
los QR son enlaces: escaneados con la **cámara nativa del celular** abren la app y, tras iniciar sesión,
inscriben al alumno (`?inscribir=<código>&f=<firma>`) o registran su presente (`?asistencia=<token>`).
El token de asistencia se valida al abrir el enlace, así el alumno tiene hasta 10 minutos para iniciar sesión
o crear su cuenta. Si todavía no estaba inscripto en esa materia, se lo inscribe y se registra el presente en el
mismo paso (el docente puede darlo de baja desde «Alumnos inscriptos»).
En local, los QR contienen el código `SIA:` firmado y se leen con el escáner integrado de la app.

## Flujo

| Acción | Quién | Cómo |
|---|---|---|
| Inscripción | Alumno | Escanea el QR de la materia o tipea el código `SIA-XXXXXX` |
| Presente (opción A) | Docente | Escanea con la cámara la credencial `SIA:STUDENT:<dni>:<firma>` del alumno |
| Presente (opción B) | Alumno | Escanea el QR dinámico proyectado (rota cada 30 s) o tipea el PIN de 6 dígitos |
| Corrección | Docente | Registro manual (presente / tarde / justificado) o anulación |

**Idempotencia:** `UNIQUE(clase_id, estudiante_id)` + `INSERT … ON CONFLICT DO NOTHING`;
un segundo escaneo responde "ya tenía presente" sin duplicar. La cámara ignora fotos ya procesadas.

**Seguridad:** contraseñas con PBKDF2-HMAC-SHA256 (200 000 iteraciones, salt por usuario),
comparación en tiempo constante, bloqueo tras 5 intentos fallidos (15 min), sesión con
expiración por inactividad (30 min) y duración máxima (8 h), credenciales y QR firmados con HMAC.

## IA: cómo se entrena

Por cada alumno-materia se toman instantáneas parciales de su historial (primeras *k* clases) y se
etiquetan con el desenlace: el **resultado final que carga el docente** (aprobado / reprobado / abandono)
o, si no existe, si terminó bajo el umbral o con ≥3 faltas consecutivas. Features: % asistencia,
máx. faltas consecutivas, faltas en las últimas 4 clases, tendencia, racha actual y clases cursadas.
La validación cruzada se agrupa por alumno para evitar fugas. Con poco historial (menos de 30 instantáneas) o sin contraste entre alumnos, el riesgo se calcula con
**reglas de asistencia** (porcentaje, faltas seguidas y últimas clases) y la interfaz lo informa como
«Análisis por reglas de asistencia».

> Mientras no haya resultados finales cargados, las etiquetas se derivan de la propia asistencia,
> por lo que el AUC reportado será optimista. Cargá los resultados al cierre de cada cursada
> (pestaña Materias → Alumnos inscriptos) para que el modelo aprenda desenlaces reales.

## Ejecutar localmente

```bash
pip install -r requirements.txt
python seed_init.py
streamlit run app.py
```

## Desplegar en Streamlit Community Cloud

1. Subí el repo a GitHub y creá la app apuntando a `app.py`.
2. En **Settings → Secrets** pegá el contenido de `.streamlit/secrets.toml.example` con valores reales
   (`SIA_SECRET` es importante: sin ella los QR se firman con una clave guardada en la propia DB).
3. `packages.txt` instala `libzbar0` para `pyzbar`; OpenCV funciona sin dependencias de sistema.

La base se crea o migra sola en cada arranque (`asegurar_esquema()`), incluso con un contenedor nuevo.

⚠️ **Persistencia en Community Cloud:** el disco del contenedor es efímero. `database.db` sobrevive entre
sesiones y recargas, pero **se pierde cuando la app se reinicia, se redespliega o entra en reposo**.
Para uso institucional real, montá la app en un servidor con disco persistente (o apuntá
`SIA_DB_PATH` a un volumen) y hacé copias periódicas de `database.db`. Las opciones para el modelo SaaS
(volumen durable, copias continuas, PostgreSQL) están en [Arquitectura, sección 5](docs/ARQUITECTURA.md).
