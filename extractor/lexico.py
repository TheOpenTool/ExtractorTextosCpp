# SPDX-License-Identifier: Apache-2.0
"""Lectura minima de C++: comentarios, literales, llamadas y argumentos.

No es un parser de C++: alcanza para encontrar llamadas a funciones conocidas
fuera de comentarios y cadenas, separar sus argumentos y saber si un argumento
es solo un literal de cadena (o varios literales seguidos).
"""
import re


def escanear(src):
    """Devuelve (mascara, literales).

    mascara: el texto con los comentarios en blanco y el contenido de las
    cadenas y caracteres reemplazado por 'x' (mismas posiciones y saltos de
    linea), asi los parentesis o comas de una cadena no confunden la busqueda.
    literales: lista de (inicio, fin) de cada literal de cadena en src,
    comillas incluidas (fin exclusivo). Los literales crudos R"(...)" se
    enmascaran pero no se listan: no se extraen.
    """
    n = len(src)
    out = list(src)
    literales = []
    i = 0
    while i < n:
        c = src[i]
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = ' '
            i = j
        elif c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if src[k] != '\n':
                    out[k] = ' '
            i = j
        elif c == 'R' and i + 1 < n and src[i + 1] == '"' and \
                (i == 0 or not (src[i - 1].isalnum() or src[i - 1] == '_')):
            m = re.match(r'R"([^()\\ ]{0,16})\(', src[i:])
            if not m:
                i += 1
                continue
            cierre = ')' + m.group(1) + '"'
            j = src.find(cierre, i + m.end())
            j = n if j < 0 else j + len(cierre)
            for k in range(i + 2, j - 1):
                if src[k] != '\n':
                    out[k] = 'x'
            i = j
        elif c == '"' or c == "'":
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == '\\':
                    j += 1
                elif src[j] == '\n':
                    break
                j += 1
            j = min(j + 1, n)
            for k in range(i + 1, j - 1):
                out[k] = 'x'
            if c == '"':
                literales.append((i, j))
            i = j
        else:
            i += 1
    return ''.join(out), literales


def buscar_llamadas(mascara, nombres):
    """Posiciones (inicio_nombre, nombre, indice_parentesis) de las llamadas."""
    if not nombres:
        return []
    alternativas = '|'.join(re.escape(x) for x in sorted(nombres, key=len, reverse=True))
    patron = re.compile(r'(?<![\w:.>])(' + alternativas + r')\s*\(')
    return [(m.start(), m.group(1), m.end() - 1) for m in patron.finditer(mascara)]


def separar_argumentos(mascara, apertura):
    """Argumentos de la llamada cuyo '(' esta en apertura.

    Devuelve (lista de (inicio, fin) de cada argumento, indice del ')').
    """
    pares = {'(': ')', '[': ']', '{': '}'}
    pila = []
    args = []
    inicio = apertura + 1
    i = apertura + 1
    while i < len(mascara):
        c = mascara[i]
        if c in pares:
            pila.append(pares[c])
        elif c in ')]}':
            if not pila:
                if c == ')':
                    if mascara[inicio:i].strip():
                        args.append((inicio, i))
                    return args, i
                return args, i
            pila.pop()
        elif c == ',' and not pila:
            args.append((inicio, i))
            inicio = i + 1
        i += 1
    return args, len(mascara)


def literales_del_argumento(mascara, literales, inicio, fin):
    """Si el argumento es SOLO literales de cadena, devuelve sus spans; si no, None."""
    dentro = [(a, b) for (a, b) in literales if a >= inicio and b <= fin]
    if not dentro:
        return None
    resto = list(mascara[inicio:fin])
    for a, b in dentro:
        for k in range(a - inicio, b - inicio):
            resto[k] = ' '
    if ''.join(resto).strip():
        return None
    return dentro


def contiene_literal(literales, inicio, fin):
    return any(a >= inicio and b <= fin for (a, b) in literales)


def numero_de_linea(src, pos):
    return src.count('\n', 0, pos) + 1
