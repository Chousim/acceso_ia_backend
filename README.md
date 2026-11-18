# RutaAccesible IA — Backend en Python (FastAPI + Google Gemini API)

Backend en **Python** desarrollado para el **Hackatón Nacional de Innovación con IA Aplicada 2026 (UVM - Ingenio Incluyente)**, diseñado para conectarse con la aplicación móvil en Flutter ([ruta-accesible-ia](https://github.com/Toothed20/ruta-accesible-ia)).

Su objetivo es asistir a **personas con discapacidad motriz** (usuarios de silla de ruedas, muletas o bastón) y **adultos mayores** evaluando en segundos qué tan seguro y accesible es un cruce peatonal o banqueta mediante fotografía y/o consulta por voz.

---

## Alineación con ODS

- **ODS 10 (Reducción de las Desigualdades):** Promueve la autonomía e inclusión generando diagnósticos claros y advertencias auditivas breves pensadas para lectura en voz alta.
- **ODS 11 (Ciudades y Comunidades Sostenibles):** Facilita la identificación temprana de barreras arquitectónicas, ausencia de rampas y obstáculos peatonales en el entorno urbano.

---

## Estructura del Repositorio

```text
acceso_ia_backend/
├── evaluar_accesibilidad.py   # Lógica multimodal con Google GenAI SDK (Paso 1 y 2)
├── main.py                    # Servidor FastAPI (GET /health, POST /evaluar, Swagger /docs)
├── test_backend.py            # Pruebas unitarias (12 tests con mocks)
├── requirements.txt           # Dependencias de Python
├── .env.example               # Plantilla de variables de entorno (sin claves reales)
├── .gitignore                 # Exclusión de .env, .venv y cachés de Python
└── README.md
```

---

## Instalación y Ejecución

1. **Crear y activar un entorno virtual:**
   ```powershell
   python -m venv .venv
   # En Windows (PowerShell):
   .\.venv\Scripts\Activate.ps1
   # En macOS / Linux:
   source .venv/bin/activate
   ```

2. **Instalar dependencias:**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Configurar la clave de Google Gemini API:**
   Copia `.env.example` a `.env` y coloca tu clave obtenida en [Google AI Studio](https://aistudio.google.com/):
   ```powershell
   Copy-Item .env.example .env
   ```
   Edita `.env`:
   ```env
   GEMINI_API_KEY=tu_clave_de_gemini_aqui
   GEMINI_MODEL=gemini-3.5-flash
   PORT=8000
   ```

4. **Iniciar el servidor FastAPI:**
   ```powershell
   python main.py
   ```
   - Estado del servidor: `GET http://localhost:8000/health`
   - Documentación interactiva (Swagger UI): `http://localhost:8000/docs`
   - Endpoint principal: `POST http://localhost:8000/evaluar` (acepta `multipart/form-data` con `imagen` y `consulta_voz`, o `application/json` con `consulta_voz`).

5. **Conectar desde el Frontend en Flutter:**
   - Emulador Android:
     ```powershell
     flutter run --dart-define=BACKEND_API_URL=http://10.0.2.2:8000/evaluar
     ```
   - Teléfono físico Android (misma red Wi-Fi):
     ```powershell
     flutter run --dart-define=BACKEND_API_URL=http://TU_IP_LOCAL:8000/evaluar
     ```

---

## Pruebas Automatizadas

```powershell
python -m unittest test_backend.py -v
```

---

## Declaración Ética del Uso de IA

En cumplimiento con los lineamientos de transparencia del Caso de Estudio y del **Hackatón Nacional de Innovación con IA Aplicada 2026**, se declara explícitamente qué módulos emplean Inteligencia Artificial:

- **Análisis multimodal (`evaluar_accesibilidad.py` y `main.py`):** Utiliza el SDK oficial `google-genai` con `gemini-3.5-flash` (y respaldo automático ante saturación a `gemini-3.1-flash-lite`, `gemini-3.6-flash`, `gemini-flash-latest` y `gemini-3.8-flash`, actualizado desde `gemini-2.5-flash` del caso de estudio por vigencia de la API de Google para claves nuevas) bajo el *System Prompt* de accesibilidad urbana y diseño universal.

| Módulo del Proyecto | Herramienta de IA | Rol y Alcance de la IA |
| :--- | :--- | :--- |
| **Análisis de Infraestructura** | Google Gemini API (`gemini-3.5-flash` / `gemini-3.1-flash-lite`) | Detección visual de obstáculos peatonales, presencia de rampas, cálculo de nivel de riesgo (`Bajo`, `Medio`, `Alto`) y generación de advertencia auditiva. |
| **Prototipado de Prompts** | Google AI Studio | Diseño, validación y depuración de las instrucciones del sistema (*System Instructions*) y esquema JSON estructurado. |
| **Documentación y Pitch** | Google Workspace (Docs / Slides) | Generación de borradores para la memoria técnica y apoyo en guion de presentación. |

---

## Referencias (Formato APA 7.ª Edición)

- Google. (2026). *Google GenAI SDK Documentation and Gemini API Reference*. Google AI for Developers. https://ai.google.dev/docs
- Naciones Unidas. (2015). *Objetivos de Desarrollo Sostenible: ODS 11 Ciudades y comunidades sostenibles*. ONU. https://www.un.org/sustainabledevelopment/es/cities/
- Universidad del Valle de México. (2026). *Bases Generales y Convocatoria: Hackatón Nacional de Innovación con IA Aplicada 2026 - Ingenio Incluyente*. Dirección Nacional de Programas de Ingeniería.
