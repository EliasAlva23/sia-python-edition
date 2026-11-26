# Arquitectura del Sistema — SIA

**Sistema de Asistencia Inteligente — plataforma multi-institución**  
Tech & Innovation Team · Institución inicial: Instituto de Educación Superior N° 11  
Versión del documento: noviembre de 2026 (esquema de datos v4)  

---

## 1. Visión general

SIA es una aplicación web en **Streamlit** organizada en cuatro capas:

| Capa | Carpeta | Responsabilidad |
|---|---|---|
| Presentación | `views/` | Paneles por perfil, componentes visuales, gráficos, escáner QR, PWA y estilos. |
| Dominio | `models/` | Clases de negocio (POO): personas, instituciones, materias, asistencia, justificativos y predictor de IA. |
| Infraestructura | `core/` | Base de datos, sesiones, seguridad, validaciones, fechas, reportes PDF/Excel y Google Drive. |
| Utilidades | `utils/` | Generación y lectura de códigos QR. |

Flujo de una acción típica: la vista (`views/`) recibe la interacción, llama a un método del modelo (`models/`), que valida y persiste mediante `core/database.py`; la vista vuelve a dibujarse con el resultado.

## 2. Estructura del repositorio

```
sia-python-edition/
├── app.py                      Punto de entrada: arranque seguro de la base, sesión y ruteo por perfil
├── seed_init.py                Verifica e inicializa la base de datos
├── requirements.txt            Dependencias de Python
├── packages.txt                Paquetes del sistema para Streamlit Cloud
├── README.md                   Guía de uso y despliegue
├── .streamlit/
│   ├── config.toml             Tema y configuración del servidor
│   └── secrets.toml.example    Plantilla de Secrets (SIA_SECRET, SIA_SUPERADMINS, Drive, etc.)
├── .devcontainer/              Entorno de desarrollo para GitHub Codespaces
├── assets/
│   ├── logo_ies11.png          Logo de la institución inicial (se copia a la base al crearla)
│   ├── logo_tech.png           Logo de Tech & Innovation Team (pie de página)
│   └── LEEME.md                Cómo reemplazar los logos
├── static/                     Servido en /app/static/ (PWA)
│   ├── manifest.json           Manifiesto de la app instalable
│   └── icon-*.png              Íconos (192, 512, adaptable y Apple)
├── core/
│   ├── database.py             Esquema SQLite v4, conexiones, migraciones y asegurar_esquema()
│   ├── sesiones.py             Sesiones persistentes (token en cookie, hash en la base)
│   ├── security.py             Hash de contraseñas, firmas HMAC, lectura de Secrets
│   ├── validaciones.py         Opciones de los selectores y validaciones
│   ├── tiempo.py               Fecha y hora en la zona horaria institucional
│   ├── reportes.py             PDF de cierre de clase y planillas Excel
│   └── drive.py                Subida de archivos a Google Drive
├── models/
│   ├── persona.py              Persona (abstracta), Estudiante, Docente, Preceptor, Directivo, Administrador
│   ├── institucion.py          Instituciones, carreras, roles por institución y opciones del sistema
│   ├── justificativo.py        Justificativos: alta, aprobación en lote y justificación masiva
│   ├── materia.py              Materia: cursada, inscripciones, clases y programa PDF
│   ├── asistencia.py           RegistroAsistencia: tokens QR, PIN, marcado idempotente
│   └── predictor_ia.py         PredictorRiesgoIA: Random Forest y análisis por reglas
├── utils/
│   └── qr.py                   Genera y lee códigos QR (OpenCV / pyzbar)
├── views/
│   ├── auth.py                 Acceso por institución, registro, sesión persistente, cambio de perfil y contraseña
│   ├── docente.py              Panel docente (Materias, Clase en vivo, Lector QR, Historial)
│   ├── alumno.py               Panel estudiante (Presente, Unirme, Mi historial, Justificativos, Credencial)
│   ├── preceptor.py            Panel de Preceptoría
│   ├── directivo.py            Panel de Rectoría / Dirección
│   ├── superadmin.py           Administración general
│   ├── config_institucion.py   Formularios de identidad visual y umbrales académicos
│   ├── justificativos.py       Bandeja de aprobación y formulario del alumno
│   ├── graficos.py             Gráficos Plotly con estilo único
│   ├── escaner.py              Escáner QR en vivo (st.components.v2 + MediaDevices)
│   ├── exportar.py             Botones de CSV, Excel y Google Drive
│   ├── pwa.py                  PWA y ocultamiento de elementos de Streamlit Cloud
│   └── styles.py               Tokens por institución, paleta base, tipografía, indicadores circulares
├── scripts/
│   └── drive_autorizar.py      Autoriza Google Drive (se ejecuta una vez)
└── docs/                       Informes del sistema (.md y .pdf) y su generador
```

## 3. Módulos principales

### 3.1 `app.py`

1. Descarta módulos del proyecto desactualizados en memoria (evita errores de importación tras un redespliegue en Streamlit Cloud).
2. Configura la página y llama a `asegurar_esquema()` **en cada ejecución**, antes de cualquier consulta (ver 3.2.2).
3. Captura enlaces QR abiertos con la cámara del celular (`?asistencia=` o `?inscribir=`), los valida en el momento y los guarda como acción pendiente.
4. Restaura la sesión desde la cookie, aplica la identidad de la institución, inyecta estilos y PWA y deriva al panel del perfil activo.

### 3.2 Modelo de datos (SQLite)

| Tabla | Contenido |
|---|---|
| `instituciones` | Clientes del SaaS: identificador del enlace, nombre, logo, colores, umbrales, tolerancia «tarde», código docente, activa |
| `carreras` / `docente_carreras` | Carreras de cada institución y carreras asignadas a cada docente |
| `usuarios` | DNI, nombre, apellido, email, rol original, hash y sal de la contraseña, legajo o departamento |
| `membresias` | Roles de cada persona en cada institución (estudiante, docente, preceptor, directivo) |
| `sesiones` | Hash del token de la cookie, perfil activo, vencimiento y último uso |
| `justificativos` | Alumno, materia (o todas), período, motivo, comprobante, estado y quién lo resolvió |
| `materias` | Nombre, descripción, curso, comisión, turno, días, hora de inicio y fin, texto de horario, umbrales de regularidad y promoción, código de clase, docente, institución y carrera |
| `materia_programas` | Programa en PDF por materia (tabla aparte para no cargar el archivo al listar) |
| `inscripciones` | Alumno y materia, fecha de inscripción, resultado final |
| `clases` | Una por materia y fecha: tema, abierta o cerrada |
| `asistencias` | Una por alumno y clase (`UNIQUE`): estado, método, quién y cuándo registró |
| `clase_reportes` | PDF generado al cerrar cada clase |
| `intentos_login` | Intentos de acceso para el bloqueo temporal |
| `config` | Versión del esquema y clave HMAC generada si no se configuró `SIA_SECRET` |

Las migraciones son automáticas: `init_db()` crea las tablas faltantes y agrega columnas nuevas a bases existentes sin perder datos (versión de esquema actual: 4). La migración a la v4 reconstruye las tablas cuyas restricciones `CHECK` cambiaron, crea la institución inicial (IES N° 11) y convierte el rol de cada usuario en una membresía de esa institución.

### 3.2.1 Multi-institución, roles y sesiones

- `models/institucion.py`: instituciones, carreras, membresías (`roles_de`, `asignar_rol`, `quitar_rol`) y opciones del sistema.
- `core/sesiones.py`: token aleatorio en la cookie `sia_sesion`; la base guarda solo su hash SHA-256. `views/auth.py`
  restaura la sesión desde la cookie al recargar y escribe las cookies al final de cada ejecución.
- `app.py` rutea por perfil activo a `views/alumno.py`, `docente.py`, `preceptor.py`, `directivo.py` o `superadmin.py`.
- `views/styles.py` genera los tokens de diseño desde los colores de la institución activa; `views/graficos.py`
  centraliza los gráficos (una serie con el color institucional, varias con paleta categórica fija, estados con texto).

### 3.2.2 Arranque e inicialización de la base

`core/database.py` expone `asegurar_esquema()`:

1. `esquema_al_dia()` comprueba con una consulta liviana que el archivo exista, que estén las tablas clave (`instituciones`, `membresias`, `sesiones`, `config`), que `schema_version` sea la actual (4) y que haya al menos una institución.
2. Si algo falta, toma un *lock* de proceso, vuelve a comprobar (otro hilo pudo haber migrado) y ejecuta `init_db()`: reconstruye las tablas con `CHECK` viejos, crea las tablas e índices que faltan, agrega columnas, crea la institución inicial y convierte los roles antiguos en membresías. Todo es idempotente.
3. Si la base no se puede preparar, la app muestra un mensaje en pantalla y se detiene sin traceback.

**Por qué no se usa `st.cache_resource`:** en Streamlit Cloud el proceso de Python sobrevive a las actualizaciones del repositorio. La versión anterior cacheaba `init_db()` en una función cuyo código no cambió, así que tras publicar la v4 el resultado cacheado de la v3 seguía vigente, la migración nunca corría y la primera consulta fallaba con `sqlite3.OperationalError: no such table: instituciones`. La comprobación por ejecución cuesta una consulta y elimina ese riesgo.

Escenarios verificados: base inexistente (contenedor nuevo), base v3 con usuarios (se migra y conserva datos y roles), 12 hilos arrancando a la vez y arranque completo de la app sobre una base v3 sin migrar.

### 3.3 Asistencia por QR

| Código | Formato | Quién lo escanea |
|---|---|---|
| QR de clase (dinámico) | `SIA:C:<clase>:<ventana>:<firma>` o enlace `?asistencia=` | Estudiante |
| PIN | 6 dígitos derivados de la misma ventana | Estudiante (sin cámara) |
| Credencial | `SIA:STUDENT:<dni>:<firma>` (fija) | Docente |
| Inscripción | `SIA:ENROLL:<código>:<firma>` o enlace `?inscribir=` | Estudiante |

Las firmas son HMAC-SHA256 con `SIA_SECRET`. La ventana del QR dinámico dura 30 segundos y se acepta la anterior. El marcado es idempotente gracias a la restricción `UNIQUE(clase_id, estudiante_id)`.

### 3.4 Escáner en vivo (`views/escaner.py`)

Componente `st.components.v2` (HTML, CSS y JavaScript que corren en la página):

1. `getUserMedia` abre la cámara elegida, la recordada o la trasera; `enumerateDevices` arma el selector.
2. Cada 150 ms decodifica un cuadro con `BarcodeDetector` nativo o, si el navegador no lo trae (Chrome y Edge en Windows), con jsQR.
3. Al leer un código, `setTriggerValue` lo envía a Python, que procesa la lectura en una única recarga. El mismo código no se reenvía durante 8 segundos.
4. Ante errores (permiso denegado, cámara en uso, sin cámara, sitio sin https) muestra un mensaje en español y el botón Reintentar.

### 3.5 Reportes y Google Drive

- `core/reportes.py`: PDF con fpdf2 y fuentes base (funciona igual en Windows y Linux); Excel con openpyxl.
- `core/drive.py`: subida multipart a Drive API v3 con google-auth, permiso `drive.file` y soporte de Unidades compartidas.

### 3.6 Sistema visual e interfaz responsiva

`views/styles.py` concentra el sistema visual:

- **Tokens de diseño** (`_variables()`): se generan en cada ejecución a partir de la institución activa. Fondo `#EEF0EC`, superficies blancas, texto marino `#142033`, acento = color principal de la institución; en modo oscuro, fondo `#0D1522` y superficies `#142033`.
- **Paleta base y presets** (`PALETAS`): «Acero y marino», «Verde azulado», «Oliva» y «Marino profundo», disponibles al crear o editar una institución.
- **Contraste automático:** `tinta_sobre()` elige texto blanco o marino; `fondo_marca()` oscurece el color hacia el marino hasta 7:1 para el panel de acceso; `_aclarar_para_oscuro()` lleva el acento a 4,5:1 en modo oscuro.
- **Tipografía:** Plus Jakarta Sans por Google Fonts con `display=swap`; si no carga, Inter y la fuente del sistema.
- **Indicadores circulares:** `kpi_grid()` recibe `(etiqueta, valor, contexto, tono[, pct])` y dibuja un anillo SVG (`anillo_html`) cuyo arco usa `pathLength=100`; si el valor es «NN %» el porcentaje se deduce solo. `tarjeta_progreso()` usa el mismo anillo para cada materia del alumno.
- **Componentes:** `tabla_html` (tarjetas en pantallas angostas), `grilla_historial`, `banner_riesgo`, `panel_login` y `titulo_login`.
- **Gráficos** (`views/graficos.py` + `estilo_plotly`): misma tipografía, grilla fina, una sola escala, etiquetas largas partidas en renglones (`partir`), leyenda debajo del gráfico con margen propio, una serie con el color institucional y varias con una paleta categórica validada en orden fijo.

Resultado: ninguna vista tiene scroll horizontal (verificado en 375 y 1024 px).

## 4. Configuración (Secrets)

| Clave | Uso |
|---|---|
| `SIA_SECRET` | Clave HMAC de QR y credenciales. **Obligatoria en producción.** |
| `SIA_DOCENTE_CODE` | Código de alta docente por defecto (cada institución puede definir el suyo). |
| `SIA_SUPERADMINS` | DNIs con acceso a la Administración general, separados por comas. |
| `SIA_PUBLIC_URL` | URL pública para que los QR sean enlaces (opcional; se detecta sola). |
| `SIA_TZ` / `SIA_SESSION_MINUTES` | Zona horaria y minutos de inactividad (opcionales). |
| `SIA_DRIVE_FOLDER_ID` | Carpeta de destino en Google Drive. |
| `SIA_DRIVE_SERVICE_ACCOUNT` | JSON de la cuenta de servicio (modo 1). |
| `SIA_DRIVE_CLIENT_ID`, `SIA_DRIVE_CLIENT_SECRET`, `SIA_DRIVE_REFRESH_TOKEN` | Cuenta de Google autorizada (modo 2). |

### Google Drive

**Modo 1 — Cuenta de servicio (Google Workspace con Unidades compartidas):** crear una cuenta de servicio en Google Cloud con la API de Drive habilitada, descargar su JSON, compartir con su email una carpeta dentro de una Unidad compartida (rol Editor) y cargar `SIA_DRIVE_SERVICE_ACCOUNT` y `SIA_DRIVE_FOLDER_ID`.

**Modo 2 — Cuenta de Google autorizada (sirve con cuentas @gmail.com):** crear un "ID de cliente de OAuth" de tipo App de escritorio, ejecutar una vez `python scripts/drive_autorizar.py client_secret.json` y pegar en Secrets los valores que muestra, más `SIA_DRIVE_FOLDER_ID` (la parte final de la URL de la carpeta).

Mientras Drive no esté configurado, los botones "Enviar a Google Drive" aparecen deshabilitados con una explicación.

## 5. Despliegue y persistencia de datos

### 5.1 Streamlit Community Cloud (estado actual)

1. Subir el repositorio a GitHub y crear la app apuntando a `app.py`.
2. Cargar los Secrets (al menos `SIA_SECRET` y `SIA_SUPERADMINS`).
3. `packages.txt` instala `libzbar0`; `requirements.txt`, las dependencias de Python.
4. Cada actualización del repositorio se aplica sola; la base se migra en la primera ejecución gracias a `asegurar_esquema()`.

**Limitación:** el disco del contenedor es efímero. `database.db` sobrevive a recargas y sesiones, pero **se pierde al reiniciar, redesplegar o cuando la app entra en reposo** por inactividad. Al volver, la app arranca con una base nueva (con la institución inicial) sin errores, pero sin los datos anteriores. Sirve para demostraciones y pilotos, no para el servicio comercial.

### 5.2 Opciones para producción (modelo SaaS)

| Opción | Cómo se implementa | Cuándo conviene |
|---|---|---|
| **A. Contenedor con volumen durable** (recomendada a corto plazo) | Ejecutar la app con Docker en un proveedor con discos persistentes (por ejemplo Render, Railway, Fly.io o una VM) montando un volumen en `/data` y definiendo `SIA_DB_PATH=/data/database.db`. No requiere cambios de código. SQLite en modo WAL soporta bien varias sesiones simultáneas en **una** instancia. | Decenas de instituciones y cientos de usuarios concurrentes con una sola instancia. |
| **B. Copias continuas** (complemento de A) | Replicar la base a un almacenamiento de objetos (S3, R2 o GCS) con Litestream, o programar `sqlite3 database.db ".backup …"` diario con retención. Restaurar = descargar el archivo y apuntar `SIA_DB_PATH`. | Siempre que se use SQLite en producción. |
| **C. Base externa gestionada** (mediano plazo) | PostgreSQL gestionado (Neon, Supabase, Amazon RDS, Cloud SQL). Requiere adaptar `core/database.py` (conexión por URL en Secrets, por ejemplo con SQLAlchemy y psycopg) y portar las migraciones; el resto del código usa SQL estándar y la capa `get_connection()`. **Todavía no está implementado.** | Varias instancias de la app en paralelo, alta disponibilidad o requisitos de auditoría y respaldo gestionados. |

Recomendación: pasar a la opción **A + B** antes de incorporar instituciones con datos reales y planificar **C** cuando el volumen lo justifique. No conviene seguir en Streamlit Community Cloud para el servicio comercial.

## 6. Verificación

| Control | Herramienta |
|---|---|
| Sintaxis de todos los módulos | `python -m compileall` |
| Estilo y errores comunes | `ruff check --select E,F,W,B` |
| Arranque de la base (vacía, v3 heredada, 12 hilos, app sobre v3 sin migrar) | Script con bases temporales y `AppTest` |
| Todas las vistas: login y 5 perfiles en 2 instituciones, modo claro y oscuro (17 casos) | `streamlit.testing.v1.AppTest` |
| Login, persistencia al recargar, marca blanca, indicadores circulares y scroll horizontal | Navegador real en 375 y 1024 px, claro y oscuro |

## 7. Generación de estos documentos

Los PDF de `docs/` se generan a partir de los `.md`:

```
pip install markdown fpdf2
python docs/generar_pdfs.py
```
