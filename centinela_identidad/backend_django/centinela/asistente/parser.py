"""Parser incremental del stream del LLM.

Formato que emite el modelo:
    <frase(s) para decir en voz>
    <<<ACCION>>>
    {json con tipo, destino, datos_*}

feed() recibe trozos y devuelve oraciones completas en cuanto cierran, para mandarlas
a voz mientras el resto sigue llegando. finish() devuelve la última oración y la acción.
"""
import json
import re

MARCA = "<<<ACCION>>>"
_FIN_ORACION = re.compile(r"(?<=[.!?…])\s+|\n+")
MIN_CHARS = 14  # oraciones más cortas se unen con la siguiente ("Claro." + ...)


class ParserStream:
    def __init__(self):
        self.buf = ""          # texto hablado aún sin cerrar oración
        self.json_buf = ""     # lo que viene después de la marca
        self.en_accion = False
        self.activar_sos = False
        self._pend = ""        # posible prefijo de marca a medio llegar
        self.frases = []       # todas las oraciones emitidas

    def _limpiar(self, s):
        if "ACTIVAR_SOS" in s:
            self.activar_sos = True
            s = s.replace("ACTIVAR_SOS", "")
        return s

    def feed(self, chunk):
        """→ lista de oraciones completas nuevas."""
        out = []
        if self.en_accion:
            self.json_buf += chunk
            return out
        texto = self._pend + chunk
        self._pend = ""
        i = texto.find(MARCA)
        if i >= 0:
            self.buf += texto[:i]
            self.json_buf += texto[i + len(MARCA):]
            self.en_accion = True
        else:
            # guardar cola que podría ser el inicio de la marca
            retener = 0
            for k in range(min(len(MARCA) - 1, len(texto)), 0, -1):
                if MARCA.startswith(texto[-k:]):
                    retener = k
                    break
            self._pend = texto[len(texto) - retener:] if retener else ""
            self.buf += texto[:len(texto) - retener]
        out.extend(self._cortar())
        return out

    def _cortar(self):
        out = []
        while True:
            # primer final de oración que deje una oración de al menos MIN_CHARS
            m = next((x for x in _FIN_ORACION.finditer(self.buf) if x.start() >= MIN_CHARS), None)
            if not m:
                break
            oracion = self._limpiar(self.buf[:m.start()]).strip()
            self.buf = self.buf[m.end():]
            if oracion:
                out.append(oracion)
                self.frases.append(oracion)
        return out

    def finish(self):
        """→ (oraciones_restantes, accion_dict|None)."""
        resto = []
        if not self.en_accion and self._pend:
            self.buf += self._pend
            self._pend = ""
        ult = self._limpiar(self.buf).strip()
        self.buf = ""
        if ult:
            resto.append(ult)
            self.frases.append(ult)
        return resto, self._parsear_json()

    def _parsear_json(self):
        s = self.json_buf.strip()
        if not s:
            return None
        if s.startswith("```"):
            s = "\n".join(l for l in s.split("\n") if not l.strip().startswith("```")).strip()
        a, b = s.find("{"), s.rfind("}")
        if a < 0 or b < a:
            return None
        try:
            d = json.loads(s[a:b + 1])
            return d if isinstance(d, dict) else None
        except json.JSONDecodeError:
            return None
