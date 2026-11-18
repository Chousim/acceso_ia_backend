import io
import os
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError

from evaluar_accesibilidad import (
    DiagnosticoAccesibilidadSchema,
    MODEL_NAME,
    _clave_gemini_valida,
    evaluar_accesibilidad_multimodal,
    preparar_imagen,
)

load_dotenv()

app = FastAPI(
    title="RutaAccesible IA — Backend API",
    description=(
        "API en Python con Google Gemini (gemini-3.5-flash con respaldo automático) "
        "para evaluar la accesibilidad urbana de banquetas y cruces peatonales mediante fotografía y voz."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
@app.get("/health")
async def health_check():
    """Verifica el estado del servidor y la configuración de GEMINI_API_KEY."""
    return {
        "status": "ok",
        "proyecto": "RutaAccesible IA",
        "modelo": MODEL_NAME,
        "gemini_api_key_configurada": bool(_clave_gemini_valida()),
        "endpoint_principal": "/evaluar",
    }


def _cargar_imagen_desde_bytes(contenido_bytes: bytes) -> Image.Image:
    """Abre y normaliza una imagen desde bytes en memoria."""
    try:
        with Image.open(io.BytesIO(contenido_bytes)) as img:
            return preparar_imagen(img)
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(
            status_code=400,
            detail="El archivo enviado en 'imagen' no es una imagen válida.",
        ) from exc


@app.post(
    "/evaluar",
    response_model=DiagnosticoAccesibilidadSchema,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "imagen": {
                                "type": "string",
                                "format": "binary",
                                "description": "Fotografía de la banqueta o cruce peatonal.",
                            },
                            "consulta_voz": {
                                "type": "string",
                                "description": "Consulta o descripción opcional por voz.",
                            },
                        },
                    }
                },
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "consulta_voz": {
                                "type": "string",
                                "example": "Hay un auto sobre la rampa, ¿es seguro pasar?",
                            },
                            "ruta_imagen": {
                                "type": "string",
                                "description": "Ruta local opcional en el servidor.",
                            },
                        },
                    }
                },
            },
        }
    },
)
async def evaluar_infraestructura(request: Request):
    """
    Endpoint principal consumido por la app móvil en Flutter (AccessibilityApiService).
    Soporta tanto peticiones multipart/form-data (con archivo 'imagen' y 'consulta_voz')
    como peticiones application/json (con 'consulta_voz' y/o 'ruta_imagen').
    """
    content_type = request.headers.get("content-type", "").lower()
    imagen_pil: Optional[Image.Image] = None
    consulta_voz: Optional[str] = None

    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        try:
            consulta_raw = form.get("consulta_voz")
            if isinstance(consulta_raw, str):
                consulta_voz = consulta_raw.strip()

            archivo_imagen = form.get("imagen")
            if archivo_imagen is not None and hasattr(archivo_imagen, "read"):
                contenido_bytes = await archivo_imagen.read()
                if contenido_bytes:
                    imagen_pil = _cargar_imagen_desde_bytes(contenido_bytes)
        finally:
            await form.close()
    else:
        try:
            body = await request.json()
        except Exception:
            body = None

        if isinstance(body, dict):
            consulta_raw = body.get("consulta_voz")
            if isinstance(consulta_raw, str):
                consulta_voz = consulta_raw.strip()
            ruta_local = body.get("ruta_imagen")
            if isinstance(ruta_local, str) and os.path.isfile(ruta_local):
                try:
                    with Image.open(ruta_local) as img:
                        imagen_pil = preparar_imagen(img)
                except (UnidentifiedImageError, OSError) as exc:
                    raise HTTPException(
                        status_code=400,
                        detail="La ruta de imagen indicada no contiene una imagen válida.",
                    ) from exc

    if imagen_pil is None and not (consulta_voz and consulta_voz.strip()):
        raise HTTPException(
            status_code=400,
            detail="Debes enviar al menos una fotografía ('imagen') o una consulta por voz ('consulta_voz').",
        )

    try:
        return evaluar_accesibilidad_multimodal(
            imagen=imagen_pil,
            consulta_voz=consulta_voz,
        )
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Error en la evaluación de infraestructura con Gemini: {str(exc)}",
        ) from exc


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
