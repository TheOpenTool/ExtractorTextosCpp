# SPDX-License-Identifier: Apache-2.0
"""Contenido de los literales y nombres de los textos."""
import re
import unicodedata

ESPECIFICADOR = re.compile(r'%[-+ #0]*(\*|\d+)?(\.(\*|\d+))?(hh|h|ll|l|L|z|j|t)?[diouxXeEfFgGaAcspn%]')


def contenido(src_literales):
    """Une el interior (sin comillas) de literales adyacentes, tal como estan en el fuente."""
    return ''.join(s[1:-1] for s in src_literales)


def decodificar(interior):
    """Texto aproximado que ve el usuario (para contar letras y nombrar)."""
    try:
        return interior.encode('latin-1', 'backslashreplace').decode('unicode_escape')
    except Exception:
        return interior


def especificadores(interior):
    """Secuencia de especificadores printf (sin %%), para comparar traducciones."""
    return [m.group(0)[-1] for m in ESPECIFICADOR.finditer(interior) if m.group(0) != '%%']


def letras(texto):
    return sum(1 for c in texto if c.isalpha())


def nombre_para(texto, max_palabras):
    sin_formato = ESPECIFICADOR.sub(' ', texto)
    plano = unicodedata.normalize('NFKD', sin_formato).encode('ascii', 'ignore').decode()
    palabras = re.findall(r'[A-Za-z0-9]+', plano)[:max_palabras]
    nombre = ''.join(p[:1].upper() + p[1:] for p in palabras) or 'Texto'
    if nombre[0].isdigit():
        nombre = 'N' + nombre
    return nombre


def clave_flexible(interior):
    """Forma para comparar textos sin importar tildes, mayusculas ni espacios
    repetidos: "Vida minima" y "Vida m\u00ednima" son el mismo texto."""
    texto = unicodedata.normalize('NFKD', decodificar(interior))
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return ' '.join(texto.lower().split())
