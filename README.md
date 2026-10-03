# 🎓 SIA · IES N° 11 — Sistema de Asistencia Inteligente (Python Edition)

Instituto de Educación Superior N° 11.

Aplicación web en **Streamlit** para la relación Docente–Alumno: asistencia por QR,
ciencia de datos con `pandas` + `plotly` y predicción de riesgo con **Random Forest** (`scikit-learn`).

## Estructura

```
app.py                      # punto de entrada (st.set_page_config wide + ruteo por rol)
seed_init.py                # verifica / inicializa database.db (opcional: --crear-docente)
core/
  database.py               # SQLite (sqlite3): esquema, conexiones transaccionales
  security.py               # PBKDF2-HMAC-SHA256 + salt, firmas HMAC, lectura de secrets
  tiempo.py                 # fechas en zona horaria institucional
models/
  persona.py                # Persona (ABC) → Docente / Estudiante + RepositorioPersonas
  materia.py                # Materia: inscripciones, clases, matriz y datos para análisis
  asistencia.py             # RegistroAsistencia: tokens QR/PIN con idempotencia
  predictor_ia.py           # PredictorRiesgoIA: Random Forest + fallback heurístico
utils/qr.py                 # generación (qrcode) y lectura (OpenCV, respaldo pyzbar)
views/                      # auth, panel docente, panel alumno, estilos CSS
.streamlit/config.toml      # tema visual
requirements.txt / packages.txt
```

## Identidad visual

- **Paleta:** `#B78FB6` (lila, acentos), `#7979B1` (lavanda, secundarios/hover), `#346FB0` (azul, botones y bordes),
  `#02447B` (tarjetas en oscuro) y `#003467` (fondo en oscuro).
- **Tipografía:** Plus Jakarta Sans (con Inter y Nunito de respaldo), cargada desde Google Fonts.
- **Pestañas tipo píldora**, tarjetas con bordes de 18 px y botones redondeados con sombras suaves.
- **Logos:** `assets/logo_ies.png` (encabezado y barra lateral) y `assets/logo_tech.png` (pie de página). Ver `assets/LEEME.md`.
- **Modo claro / oscuro:** interruptor "🌙 Modo oscuro" en el menú ☰ de la barra superior.
- **Sin encabezado ni barra lateral de Streamlit:** están ocultos; tema, cambiar contraseña y cerrar sesión están en el menú ☰, y la materia activa del docente se elige arriba de las pestañas.

## Instalación en el celular (PWA)

La app agrega el manifiesto (`static/manifest.json`), los íconos y las etiquetas `<meta>` necesarias para
"Agregar a pantalla principal" en Android (Chrome) e iOS (Safari → Compartir → Agregar a inicio).
Requiere `server.enableStaticServing = true` en `.streamlit/config.toml` (ya configurado).

## Materias

Cada materia exige **Curso / Comisión**, **Turno** (Mañana / Tarde / Noche) y **Día y horario**.
Las bases creadas con la versión anterior se migran solas al iniciar (se agregan las columnas sin perder datos).

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
La validación cruzada se agrupa por alumno para evitar fugas. Con menos de 30 instantáneas se usa un
puntaje heurístico y la interfaz lo indica.

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

⚠️ **Persistencia en Community Cloud:** el disco del contenedor es efímero. `database.db` sobrevive entre
sesiones y recargas, pero **se pierde cuando la app se reinicia, se redespliega o entra en reposo**.
Para uso institucional real, montá la app en un servidor con disco persistente (o apuntá
`SIA_DB_PATH` a un volumen) y hacé copias periódicas de `database.db`.
