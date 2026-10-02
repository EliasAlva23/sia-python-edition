"""Predicción de riesgo de deserción/reprobación con Random Forest (scikit-learn).

Estrategia de entrenamiento (sin datos inventados):
  Para cada alumno-materia con historia suficiente se generan "instantáneas" parciales
  (las primeras k clases) y se etiquetan con el desenlace final:
    * el resultado cargado por el docente (aprobado / reprobado / abandono), si existe;
    * si no, si la asistencia final quedó bajo el umbral o hubo una racha de faltas.
  Así el modelo aprende a anticipar el desenlace a partir de historia incompleta.

Si todavía no hay datos suficientes (o una sola clase de etiqueta), se usa un
puntaje heurístico transparente y la interfaz lo informa explícitamente.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedGroupKFold, cross_val_score

ETIQUETAS_FEATURES = {
    "pct_asistencia": "% asistencia",
    "max_consecutivas": "Máx. faltas consecutivas",
    "ausencias_recientes": "Faltas en últimas 4 clases",
    "tendencia": "Tendencia (2ª mitad − 1ª)",
    "racha_actual": "Racha actual de faltas",
    "n_clases": "Clases cursadas",
}


class PredictorRiesgoIA:
    FEATURES = list(ETIQUETAS_FEATURES)
    MIN_MUESTRAS = 30
    MIN_HISTORIA = 3

    def __init__(
        self,
        umbral: float = 75.0,
        max_consecutivas: int = 3,
        n_estimators: int = 300,
        random_state: int = 42,
    ) -> None:
        self._umbral = float(umbral)
        self._max_consecutivas = int(max_consecutivas)
        self._n_estimators = n_estimators
        self._random_state = random_state
        self._modelo: RandomForestClassifier | None = None
        self._info: dict = {"modo": "heuristico"}

    @property
    def modo(self) -> str:
        return self._info["modo"]

    @property
    def info(self) -> dict:
        return dict(self._info)

    # ----- ingeniería de features -----
    @staticmethod
    def extraer_features(secuencia: list[int]) -> dict:
        arr = np.asarray(secuencia, dtype=int)
        n = len(arr)
        if n == 0:
            return {"pct_asistencia": 100.0, "max_consecutivas": 0, "ausencias_recientes": 0,
                    "tendencia": 0.0, "racha_actual": 0, "n_clases": 0}
        max_c = actual = 0
        for valor in arr:
            actual = actual + 1 if valor == 0 else 0
            max_c = max(max_c, actual)
        tendencia = 0.0
        if n >= 4:
            mitad = n // 2
            tendencia = float((arr[mitad:].mean() - arr[:mitad].mean()) * 100)
        return {
            "pct_asistencia": float(arr.mean() * 100),
            "max_consecutivas": int(max_c),
            "ausencias_recientes": int((arr[-4:] == 0).sum()),
            "tendencia": tendencia,
            "racha_actual": int(actual),
            "n_clases": int(n),
        }

    @staticmethod
    def _secuencias(df: pd.DataFrame) -> dict[str, list[int]]:
        ordenado = df.sort_values(["clave", "fecha"])
        return ordenado.groupby("clave")["presente"].apply(list).to_dict()

    def _etiqueta(self, secuencia: list[int], resultado: str | None) -> int:
        if resultado in ("reprobado", "abandono"):
            return 1
        if resultado == "aprobado":
            return 0
        f = self.extraer_features(secuencia)
        return int(f["pct_asistencia"] < self._umbral or f["max_consecutivas"] >= self._max_consecutivas)

    def construir_dataset(
        self, df: pd.DataFrame, resultados: dict[str, str] | None = None
    ) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
        resultados = resultados or {}
        filas, etiquetas, grupos = [], [], []
        for clave, secuencia in self._secuencias(df).items():
            if len(secuencia) <= self.MIN_HISTORIA and clave not in resultados:
                continue
            etiqueta = self._etiqueta(secuencia, resultados.get(clave))
            limite = len(secuencia) + 1 if clave in resultados else len(secuencia)
            for k in range(min(self.MIN_HISTORIA, len(secuencia)), limite):
                if k == 0:
                    continue
                filas.append(self.extraer_features(secuencia[:k]))
                etiquetas.append(etiqueta)
                grupos.append(clave)
        X = pd.DataFrame(filas, columns=self.FEATURES)
        return X, np.asarray(etiquetas, dtype=int), np.asarray(grupos)

    # ----- entrenamiento -----
    def entrenar(self, df: pd.DataFrame, resultados: dict[str, str] | None = None) -> dict:
        X, y, grupos = self.construir_dataset(df, resultados)
        info = {
            "modo": "heuristico",
            "muestras": int(len(X)),
            "alumnos": int(len(set(grupos))),
            "positivos": int(y.sum()) if len(y) else 0,
            "etiquetas_docente": len(resultados or {}),
        }
        if len(X) < self.MIN_MUESTRAS or len(np.unique(y)) < 2:
            info["motivo"] = (
                f"Se necesitan al menos {self.MIN_MUESTRAS} instantáneas de historia con casos de ambas "
                f"clases (hay {len(X)}). Mientras tanto se usa un puntaje heurístico."
            )
            self._modelo, self._info = None, info
            return dict(info)

        modelo = RandomForestClassifier(
            n_estimators=self._n_estimators,
            max_depth=6,
            min_samples_leaf=2,
            class_weight="balanced",
            random_state=self._random_state,
            n_jobs=-1,
        )
        # Validación agrupada por alumno: evita que instantáneas del mismo alumno se filtren entre folds.
        grupos_por_clase = min(len(set(grupos[y == c])) for c in (0, 1))
        n_splits = min(5, grupos_por_clase)
        if n_splits >= 2:
            try:
                cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=self._random_state)
                scores = cross_val_score(modelo, X, y, groups=grupos, cv=cv, scoring="roc_auc")
                if not np.isnan(scores).all():
                    info["auc_cv"] = float(np.nanmean(scores))
                    info["folds"] = n_splits
            except ValueError:
                pass
        modelo.fit(X, y)
        info["modo"] = "random_forest"
        self._modelo, self._info = modelo, info
        return dict(info)

    # ----- predicción -----
    def _prob_heuristica(self, f: dict) -> float:
        z = (
            6 * (self._umbral - f["pct_asistencia"]) / 100
            + 0.9 * f["max_consecutivas"]
            + 0.5 * f["ausencias_recientes"]
            + 0.7 * f["racha_actual"]
            - 0.02 * f["tendencia"]
            - 1.5
        )
        return 1 / (1 + math.exp(-z))

    def predecir(self, df: pd.DataFrame) -> pd.DataFrame:
        columnas = ["clave", "materia", "alumno", "dni", "estudiante_id", *self.FEATURES,
                    "prob_riesgo", "nivel", "motivos"]
        if df.empty:
            return pd.DataFrame(columns=columnas)
        identidad = df.drop_duplicates("clave").set_index("clave")[["materia", "alumno", "dni", "estudiante_id"]]
        secuencias = self._secuencias(df)
        filas = []
        for clave, secuencia in secuencias.items():
            filas.append({"clave": clave, **identidad.loc[clave].to_dict(), **self.extraer_features(secuencia)})
        resultado = pd.DataFrame(filas)
        if self._modelo is not None:
            resultado["prob_riesgo"] = self._modelo.predict_proba(resultado[self.FEATURES])[:, 1]
        else:
            resultado["prob_riesgo"] = [self._prob_heuristica(f) for f in resultado[self.FEATURES].to_dict("records")]
        niveles = [self._clasificar(f) for f in resultado.to_dict("records")]
        resultado["nivel"] = [n for n, _ in niveles]
        resultado["motivos"] = [m for _, m in niveles]
        orden = {"ALTO": 0, "MEDIO": 1, "BAJO": 2}
        resultado = resultado.sort_values(
            by=["nivel", "prob_riesgo"], key=lambda s: s.map(orden) if s.name == "nivel" else -s
        )
        return resultado[columnas].reset_index(drop=True)

    def _clasificar(self, f: dict) -> tuple[str, str]:
        if f["n_clases"] == 0:
            return "BAJO", "Sin clases registradas todavía"
        motivos = []
        pct, prob = f["pct_asistencia"], f["prob_riesgo"]
        if pct < self._umbral:
            motivos.append(f"Asistencia {pct:.0f}% < {self._umbral:.0f}%")
        if f["max_consecutivas"] >= self._max_consecutivas:
            motivos.append(f"{f['max_consecutivas']} faltas consecutivas")
        if f["racha_actual"] >= 2:
            motivos.append(f"Viene faltando {f['racha_actual']} clases seguidas")
        if f["tendencia"] <= -25:
            motivos.append("Tendencia de asistencia en caída")
        if prob >= 0.6:
            motivos.append(f"Probabilidad de riesgo {prob:.0%}")
        if pct < self._umbral or f["max_consecutivas"] >= self._max_consecutivas or prob >= 0.6:
            nivel = "ALTO"
        elif prob >= 0.35 or pct < self._umbral + 10 or f["racha_actual"] >= 2:
            nivel = "MEDIO"
        else:
            nivel = "BAJO"
        return nivel, "; ".join(motivos) or "Asistencia regular"

    def importancias(self) -> pd.DataFrame:
        if self._modelo is None:
            return pd.DataFrame(columns=["feature", "importancia"])
        return (
            pd.DataFrame({
                "feature": [ETIQUETAS_FEATURES[f] for f in self.FEATURES],
                "importancia": self._modelo.feature_importances_,
            })
            .sort_values("importancia")
            .reset_index(drop=True)
        )

    @staticmethod
    def clases_para_recuperar(presentes: int, total: int, umbral: float) -> int:
        """Clases consecutivas a las que hay que asistir para volver a superar el umbral."""
        u = umbral / 100
        if total == 0 or presentes / total >= u or u >= 1:
            return 0
        return math.ceil((u * total - presentes) / (1 - u))
