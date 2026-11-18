import json
import os
from typing import Literal, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

# Cargar variables de entorno desde archivo .env si existe
load_dotenv()

# Paso 1 del Caso de Estudio: System Prompt oficial
SYSTEM_PROMPT = (
    "Eres un experto en accesibilidad urbana y diseño universal. Analiza la "
    "imagen del entorno peatonales recibida e identifica: 1) Si hay accesibilidad "
    "para sillas de ruedas, 2) Obstáculos presentes (baches, autos mal estacionados, "
    "falta de rampa), 3) Un nivel de riesgo (Bajo, Medio, Alto) y 4) Una "
    "recomendación breve de navegación por audio."
)

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip() or "gemini-3.5-flash"
FALLBACK_MODELS = (
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash",
    "gemini-flash-latest",
    "gemini-3.8-flash",
)
_PLACEHOLDER_KEYS = {"", "TU_CLAVE_GEMINI_AQUI", "tu_clave_de_gemini_aqui"}
_MAX_IMAGE_SIZE = (1600, 1600)
_RETRYABLE_STATUS_MARKERS = (
    "503",
    "429",
    "404",
    "unavailable",
    "high demand",
    "overloaded",
    "resource_exhausted",
    "not_found",
)


def _clave_gemini_valida() -> str:
    """Obtiene GEMINI_API_KEY limpia o cadena vacía si no está configurada."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key in _PLACEHOLDER_KEYS:
        return ""
    return api_key


# Configuración del cliente oficial de Gemini (Paso 2 del Caso de Estudio)
_initial_key = _clave_gemini_valida()
client = genai.Client(api_key=_initial_key) if _initial_key else None


def obtener_cliente() -> genai.Client:
    """Retorna el cliente oficial de Google GenAI validando GEMINI_API_KEY."""
    global client
    api_key = _clave_gemini_valida()
    if not api_key:
        raise ValueError(
            "La variable de entorno GEMINI_API_KEY no está configurada. "
            "Defínela en tu archivo backend/.env o en las variables del sistema."
        )
    if client is None:
        client = genai.Client(api_key=api_key)
    return client


def preparar_imagen(imagen: Image.Image) -> Image.Image:
    """Normaliza orientación EXIF, modo de color y tamaño máximo de la imagen."""
    normalizada = ImageOps.exif_transpose(imagen)
    if normalizada.mode not in ("RGB", "L"):
        normalizada = normalizada.convert("RGB")
    else:
        normalizada = normalizada.copy()
    normalizada.thumbnail(_MAX_IMAGE_SIZE)
    return normalizada


class DiagnosticoAccesibilidadSchema(BaseModel):
    """Esquema estructurado compatible con DiagnosisApiModel del frontend Flutter."""

    tiene_rampa: bool = Field(
        description="1. ¿Cuenta con rampa accesible para silla de ruedas? (true/false)"
    )
    titulo: str = Field(
        description="Resumen directo en una sola frase clara sobre el estado de la banqueta o cruce."
    )
    obstaculos_detectados: str = Field(
        description="2. Descripción clara en español de los obstáculos detectados (baches, escalones, autos mal estacionados, falta de rampa, etc.)."
    )
    nivel_riesgo: Literal["Bajo", "Medio", "Alto"] = Field(
        description="3. Nivel de riesgo para una persona con movilidad reducida: Bajo, Medio o Alto."
    )
    recomendacion: str = Field(
        description="Recomendación práctica y concreta de qué hacer ahora para avanzar con seguridad."
    )
    advertencia_auditiva: str = Field(
        description="4. Mensaje corto de advertencia auditiva en español pensado para leerse en voz alta (TTS)."
    )


def _modelos_candidatos() -> list[str]:
    """Construye la lista ordenada de modelos sin duplicados (principal + respaldo)."""
    candidatos = [MODEL_NAME, *FALLBACK_MODELS]
    vistos: set[str] = set()
    resultado: list[str] = []
    for modelo in candidatos:
        if modelo and modelo not in vistos:
            vistos.add(modelo)
            resultado.append(modelo)
    return resultado


def _es_error_recuperable_modelo(exc: Exception) -> bool:
    """Indica si el error corresponde a saturación, cuota o modelo no disponible."""
    mensaje = str(exc).lower()
    return any(marker in mensaje for marker in _RETRYABLE_STATUS_MARKERS)


def _generar_con_respaldo(
    gemini_client: genai.Client,
    contents: list,
    config: types.GenerateContentConfig,
):
    """Intenta generar contenido con el modelo principal y cae a respaldos si hay 503/429/404."""
    ultimo_error: Optional[Exception] = None
    for modelo in _modelos_candidatos():
        try:
            return gemini_client.models.generate_content(
                model=modelo,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            ultimo_error = exc
            if not _es_error_recuperable_modelo(exc):
                raise
    assert ultimo_error is not None
    raise ultimo_error


def evaluar_accesibilidad_urbana(ruta_imagen: str) -> str:
    """
    Paso 2 del Caso de Estudio:
    Analiza una fotografía del entorno peatonal y retorna una evaluación
    de accesibilidad y riesgos para movilidad reducida.
    """
    try:
        gemini_client = obtener_cliente()
        with Image.open(ruta_imagen) as img:
            imagen = preparar_imagen(img)

        prompt = (
            "Analiza esta infraestructura peatonal para una persona en silla de ruedas. "
            "Responde en formato estructurado: "
            "1. ¿Cuenta con rampa? (Sí/No) "
            "2. Obstáculos detectados. "
            "3. Nivel de riesgo (Bajo/Medio/Alto). "
            "4. Mensaje corto de advertencia auditiva."
        )

        response = _generar_con_respaldo(
            gemini_client,
            contents=[imagen, prompt],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
            ),
        )
        return response.text or "No se recibió respuesta del modelo de IA."
    except Exception as e:
        return f"Error en la evaluación de infraestructura: {str(e)}"


def evaluar_accesibilidad_multimodal(
    imagen: Optional[Image.Image] = None,
    consulta_voz: Optional[str] = None,
) -> dict:
    """
    Analiza una imagen y/o consulta por voz del usuario utilizando Gemini
    y devuelve un diccionario JSON con la estructura exacta requerida por la app Flutter.
    """
    consulta_limpia = consulta_voz.strip() if consulta_voz else ""
    if imagen is None and not consulta_limpia:
        raise ValueError(
            "Se requiere al menos una imagen o una consulta por voz para evaluar el camino."
        )

    gemini_client = obtener_cliente()

    if imagen is not None:
        prompt_base = (
            "Analiza esta infraestructura peatonal para una persona en silla de ruedas, "
            "con muletas, bastón o adulto mayor. "
            "Evalúa: "
            "1. ¿Cuenta con rampa? (tiene_rampa: true/false). "
            "2. Obstáculos detectados (obstaculos_detectados) y un resumen en una frase (titulo). "
            "3. Nivel de riesgo (nivel_riesgo: 'Bajo', 'Medio' o 'Alto'). "
            "4. Recomendación de acción (recomendacion) y mensaje corto de advertencia auditiva "
            "para lectura en voz alta (advertencia_auditiva)."
        )
    else:
        prompt_base = (
            "El usuario no envió fotografía en este momento, sino una descripción o consulta por voz "
            "sobre su entorno peatonal. Evalúa la situación descrita para una persona en silla de ruedas, "
            "con muletas, bastón o adulto mayor y responde con el diagnóstico estructurado: "
            "1. ¿Cuenta con rampa accesible según lo descrito? (tiene_rampa: true/false; usa false si está bloqueada o ausente). "
            "2. Obstáculos descritos (obstaculos_detectados) y resumen en una frase (titulo). "
            "3. Nivel de riesgo (nivel_riesgo: 'Bajo', 'Medio' o 'Alto'). "
            "4. Recomendación práctica inmediata (recomendacion) y mensaje corto para leerse en voz alta (advertencia_auditiva)."
        )

    if consulta_limpia:
        prompt_base += (
            f'\n\nConsulta o descripción por voz del usuario: "{consulta_limpia}". '
            "Tómala en cuenta y respóndela directamente dentro del diagnóstico y la advertencia auditiva."
        )

    contents = []
    if imagen is not None:
        contents.append(preparar_imagen(imagen))
    contents.append(prompt_base)

    response = _generar_con_respaldo(
        gemini_client,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=DiagnosticoAccesibilidadSchema,
            temperature=0.2,
        ),
    )

    if response.parsed is not None:
        if isinstance(response.parsed, BaseModel):
            return response.parsed.model_dump()
        if isinstance(response.parsed, dict):
            return response.parsed

    if not response.text:
        raise RuntimeError("El modelo Gemini no devolvió contenido en la respuesta.")

    return json.loads(response.text)


if __name__ == "__main__":
    resultado = evaluar_accesibilidad_urbana("banqueta_ejemplo.jpg")
    print("--- Diagnostic de Accesibilidad Peatonal ---")
    print(resultado)
