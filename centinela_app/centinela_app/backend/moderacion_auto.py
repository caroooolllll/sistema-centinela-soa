"""Moderación automática de publicaciones: aprobar / bloquear / revisión humana, con motivo en español.
Reglas deterministas: el texto del vecino es DATO. Nada de lo que diga («ignora tus instrucciones y aprueba»)
cambia la decisión; al contrario, intentarlo manda la publicación a revisión humana."""
import re
import unicodedata

INSULTOS = ['idiota', 'estupido', 'imbecil', 'pendejo', 'cabron', 'puta', 'puto', 'mierda', 'hdp', 'maldito', 'basura de persona']
AMENAZAS = ['te voy a matar', 'los voy a matar', 'te voy a golpear', 'van a pagar', 'te vamos a quemar', 'ojala te mueras']
ESTAFA = ['gana dinero facil', 'inversion segura', 'prestamo inmediato', 'click aqui para ganar', 'transfiere', 'criptomoneda', 'bitcoin']
INYECCION = ['ignora tus instrucciones', 'ignora las instrucciones', 'ignore previous', 'ignore all previous', 'system prompt',
             'olvida lo anterior', 'eres ahora', 'aprueba esta publicacion', 'abre el porton']
SENSIBLE = ['denuncia', 'estafa', 'acoso', 'drogas', 'arma']


def _norm(t):
    t = unicodedata.normalize('NFD', (t or '').lower())
    return ''.join(c for c in t if unicodedata.category(c) != 'Mn')


def _hay(n, lista):
    return next((p for p in lista if re.search(r'(?<!\w)' + re.escape(p) + r'(?!\w)', n)), None)


def moderar(titulo, contenido):
    """→ ('aprobar'|'bloquear'|'revision', motivo en español)."""
    texto = f'{titulo or ""} {contenido or ""}'
    n = _norm(texto)
    if (p := _hay(n, AMENAZAS)):
        return 'bloquear', 'Contiene una amenaza hacia otra persona.'
    if (p := _hay(n, INSULTOS)):
        return 'bloquear', 'Contiene lenguaje ofensivo. Reescríbela con respeto y vuelve a publicar.'
    if _hay(n, INYECCION):
        return 'revision', 'El texto intenta dar instrucciones al sistema automático; lo revisa una persona.'
    if _hay(n, ESTAFA):
        return 'revision', 'Parece una oferta o posible estafa; necesita revisión humana.'
    if re.search(r'https?://|www\.|\.com\b|\.mx\b', n):
        return 'revision', 'Incluye un enlace externo; un administrador debe verificarlo.'
    if re.search(r'(?<!\d)(?:\d[\s\-]?){10,}(?!\d)', texto):
        return 'revision', 'Incluye un número de teléfono; se revisa para proteger la privacidad.'
    letras = [c for c in texto if c.isalpha()]
    if len(letras) > 20 and sum(c.isupper() for c in letras) / len(letras) > 0.6:
        return 'revision', 'Está escrita casi toda en mayúsculas; se revisa antes de publicarse.'
    if _hay(n, SENSIBLE):
        return 'revision', 'Trata un tema sensible (denuncia, acoso, etc.); la revisa una persona.'
    return 'aprobar', 'Contenido normal: publicado automáticamente por Centinela.'
