"""Modelo de dominio del SIA (POO)."""
from models.asistencia import RegistroAsistencia, ResultadoMarcado
from models.materia import Materia
from models.persona import Docente, Estudiante, Persona, RepositorioPersonas
from models.predictor_ia import PredictorRiesgoIA

__all__ = [
    "Persona",
    "Docente",
    "Estudiante",
    "RepositorioPersonas",
    "Materia",
    "RegistroAsistencia",
    "ResultadoMarcado",
    "PredictorRiesgoIA",
]
