import io
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from PIL import Image

import evaluar_accesibilidad
from main import app


class TestBackendRutaAccesible(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _crear_imagen_prueba_bytes(self, mode: str = "RGB", fmt: str = "JPEG") -> bytes:
        color = (120, 120, 120, 255) if mode == "RGBA" else (120, 120, 120)
        img = Image.new(mode, (100, 100), color=color)
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        return buf.getvalue()

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["modelo"], evaluar_accesibilidad.MODEL_NAME)
        self.assertEqual(data["modelo"], "gemini-3.5-flash")
        self.assertEqual(data["endpoint_principal"], "/evaluar")

    def test_openapi_expone_formulario_imagen(self):
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        content = schema["paths"]["/evaluar"]["post"]["requestBody"]["content"]
        self.assertIn("multipart/form-data", content)
        self.assertIn("application/json", content)
        props = content["multipart/form-data"]["schema"]["properties"]
        self.assertEqual(props["imagen"]["format"], "binary")
        self.assertIn("consulta_voz", props)

    def test_rechaza_clave_placeholder(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "TU_CLAVE_GEMINI_AQUI"}):
            evaluar_accesibilidad.client = None
            with self.assertRaises(ValueError):
                evaluar_accesibilidad.obtener_cliente()

    @patch("evaluar_accesibilidad.obtener_cliente")
    def test_funcion_caso_estudio_pdf(self, mock_obtener_cliente):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = (
            "1. ¿Cuenta con rampa? No\n"
            "2. Obstáculos detectados: Escalón alto y banqueta fracturada.\n"
            "3. Nivel de riesgo: Alto\n"
            "4. Mensaje corto de advertencia auditiva: Precaución, banqueta sin rampa."
        )
        mock_client.models.generate_content.return_value = mock_response
        mock_obtener_cliente.return_value = mock_client

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(self._crear_imagen_prueba_bytes())
            tmp_path = tmp.name

        try:
            resultado = evaluar_accesibilidad.evaluar_accesibilidad_urbana(tmp_path)
            self.assertIn("Nivel de riesgo: Alto", resultado)
            mock_client.models.generate_content.assert_called_once()
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @patch("evaluar_accesibilidad.obtener_cliente")
    def test_multimodal_convierte_rgba_y_solo_voz(self, mock_obtener_cliente):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.parsed = evaluar_accesibilidad.DiagnosticoAccesibilidadSchema(
            tiene_rampa=False,
            titulo="Rampa bloqueada por vehículo.",
            obstaculos_detectados="Auto estacionado sobre la rampa peatonal.",
            nivel_riesgo="Alto",
            recomendacion="Busque el cruce alterno a mitad de cuadra.",
            advertencia_auditiva="Alto riesgo: hay un auto bloqueando la rampa.",
        )
        mock_client.models.generate_content.return_value = mock_response
        mock_obtener_cliente.return_value = mock_client

        rgba_img = Image.new("RGBA", (2000, 1000), color=(10, 20, 30, 255))
        res_img = evaluar_accesibilidad.evaluar_accesibilidad_multimodal(imagen=rgba_img)
        self.assertFalse(res_img["tiene_rampa"])
        sent_img = mock_client.models.generate_content.call_args.kwargs["contents"][0]
        self.assertEqual(sent_img.mode, "RGB")
        self.assertLessEqual(max(sent_img.size), 1600)

        res_voz = evaluar_accesibilidad.evaluar_accesibilidad_multimodal(
            consulta_voz="Hay un coche tapando la rampa"
        )
        self.assertEqual(res_voz["nivel_riesgo"], "Alto")

    @patch("main.evaluar_accesibilidad_multimodal")
    def test_post_evaluar_multipart_con_imagen_y_voz(self, mock_evaluar):
        mock_evaluar.return_value = {
            "tiene_rampa": False,
            "titulo": "La banqueta está rota y es muy peligrosa.",
            "obstaculos_detectados": "Escalón alto y baches profundos en el cruce.",
            "nivel_riesgo": "Alto",
            "recomendacion": "Cruce por la esquina opuesta que sí cuenta con rampa.",
            "advertencia_auditiva": "Atención: Alto riesgo. No hay rampa y el piso está roto.",
        }

        img_bytes = self._crear_imagen_prueba_bytes(mode="RGBA", fmt="PNG")
        response = self.client.post(
            "/evaluar",
            files={"imagen": ("banqueta.png", img_bytes, "image/png")},
            data={"consulta_voz": "¿Puedo pasar con silla de ruedas?"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["tiene_rampa"])
        self.assertEqual(body["nivel_riesgo"], "Alto")
        self.assertIn("silla de ruedas", mock_evaluar.call_args.kwargs["consulta_voz"])
        self.assertIsNotNone(mock_evaluar.call_args.kwargs["imagen"])

    @patch("main.evaluar_accesibilidad_multimodal")
    def test_post_evaluar_json_solo_voz(self, mock_evaluar):
        mock_evaluar.return_value = {
            "tiene_rampa": True,
            "titulo": "Esta banqueta es plana y segura para avanzar.",
            "obstaculos_detectados": "No se reportan obstáculos en el cruce.",
            "nivel_riesgo": "Bajo",
            "recomendacion": "Avance por el paso peatonal señalizado.",
            "advertencia_auditiva": "Camino seguro. Sí cuenta con rampa.",
        }

        response = self.client.post(
            "/evaluar",
            json={"consulta_voz": "Veo una rampa azul en la esquina, ¿es seguro cruzar?"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["tiene_rampa"])
        self.assertEqual(body["nivel_riesgo"], "Bajo")

    def test_post_evaluar_imagen_invalida_retorna_400(self):
        response = self.client.post(
            "/evaluar",
            files={"imagen": ("corrupto.jpg", b"no-es-una-imagen", "image/jpeg")},
        )
        self.assertEqual(response.status_code, 400)

    def test_post_evaluar_vacio_retorna_400(self):
        response = self.client.post("/evaluar", json={"consulta_voz": "   "})
        self.assertEqual(response.status_code, 400)

    @patch("main.evaluar_accesibilidad_multimodal", side_effect=RuntimeError("Fallo temporal"))
    def test_post_evaluar_error_gemini_retorna_502(self, _mock_evaluar):
        response = self.client.post(
            "/evaluar",
            json={"consulta_voz": "¿Es seguro cruzar?"},
        )
        self.assertEqual(response.status_code, 502)


    @patch("evaluar_accesibilidad.obtener_cliente")
    def test_respaldo_automatico_ante_503_o_404(self, mock_obtener_cliente):
        mock_client = MagicMock()
        mock_ok_response = MagicMock()
        mock_ok_response.parsed = evaluar_accesibilidad.DiagnosticoAccesibilidadSchema(
            tiene_rampa=True,
            titulo="Cruce despejado con rampa.",
            obstaculos_detectados="Ninguno.",
            nivel_riesgo="Bajo",
            recomendacion="Cruce con calma.",
            advertencia_auditiva="Camino seguro con rampa libre.",
        )

        mock_client.models.generate_content.side_effect = [
            RuntimeError("503 UNAVAILABLE. This model is currently experiencing high demand."),
            mock_ok_response,
        ]
        mock_obtener_cliente.return_value = mock_client

        resultado = evaluar_accesibilidad.evaluar_accesibilidad_multimodal(
            consulta_voz="¿Puedo pasar por la esquina?"
        )
        self.assertEqual(resultado["nivel_riesgo"], "Bajo")
        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        primer_modelo = mock_client.models.generate_content.call_args_list[0].kwargs["model"]
        segundo_modelo = mock_client.models.generate_content.call_args_list[1].kwargs["model"]
        self.assertEqual(primer_modelo, "gemini-3.5-flash")
        self.assertEqual(segundo_modelo, "gemini-3.1-flash-lite")

    @patch("evaluar_accesibilidad.obtener_cliente")
    def test_no_reintenta_error_autenticacion(self, mock_obtener_cliente):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("401 PERMISSION_DENIED: API key not valid")
        mock_obtener_cliente.return_value = mock_client

        with self.assertRaises(RuntimeError):
            evaluar_accesibilidad.evaluar_accesibilidad_multimodal(consulta_voz="Prueba")
        self.assertEqual(mock_client.models.generate_content.call_count, 1)


if __name__ == "__main__":
    unittest.main()
