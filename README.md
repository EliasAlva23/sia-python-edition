# 🎓 SIA · Sistema de Asistencia Inteligente (Python Edition)

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
