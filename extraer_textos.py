#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pasa los textos visibles de un codigo C++ a un archivo de textos posicional.

Uso:
    extraer_textos.py --config <cfg.json> <archivos...> [--aplicar]
    extraer_textos.py --config <cfg.json> --pendientes <N>
    extraer_textos.py --config <cfg.json> --traducciones <trad.json> --bloque <N>
    extraer_textos.py --config <cfg.json> --verificar [--raiz <dir>]

Modos:
    (archivos)          busca en esos archivos las llamadas de la configuracion
                        cuyo argumento de texto es un literal, y muestra que
                        texto iria al archivo de textos y con que nombre.
    --aplicar           agrega los textos nuevos al archivo de textos (bloque 0
                        con el texto, el resto vacios) y reemplaza cada literal
                        por la expresion de la plantilla. Agrega el include y la
                        declaracion de la configuracion si faltan.
    --pendientes N      JSON {nombre: texto del bloque 0} de las entradas que
                        estan vacias en el bloque N (lo que falta traducir).
    --traducciones F    carga un JSON {nombre: texto} en el bloque --bloque N.
                        Rechaza un texto cuyos % de formato no coinciden con los
                        del bloque 0.
    --verificar         comprueba el archivo de textos (bloques en orden, mismas
                        entradas en el mismo orden, nombres unicos, % iguales) y,
                        con --raiz, que todo <tipo>::<Nombre> usado en el codigo
                        exista.

Rutas relativas de la configuracion: se resuelven desde el directorio actual.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from extractor import lexico, nombres  # noqa: E402
from extractor.textos import ArchivoTextos  # noqa: E402


def cargar_config(ruta):
    cfg = json.load(open(ruta, encoding='utf-8'))
    for clave in ('archivo_textos', 'funciones', 'plantillas', 'textos'):
        if clave not in cfg:
            raise SystemExit('falta "%s" en %s' % (clave, ruta))
    return cfg


class Hallazgo:
    def __init__(self, linea, funcion, tipo, span, interior, sufijo, sin_args, original=''):
        self.linea = linea
        self.funcion = funcion
        self.tipo = tipo
        self.span = span
        self.interior = interior        # texto visible (fuente, sin comillas)
        self.sufijo = sufijo            # '##id' o '###id' de las etiquetas
        self.sin_args = sin_args
        self.original = original        # literal completo (titulos que son ID)
        self.nombre = None


def analizar(ruta, cfg):
    src = open(ruta, encoding='utf-8').read()
    mascara, literales = lexico.escanear(src)
    funciones = cfg['funciones']
    excluir = [re.compile(x) for x in cfg.get('excluir', [])]
    minimo = cfg.get('minimo_letras', 2)
    hallazgos, revisar, ids = [], [], []
    for inicio, funcion, apertura in lexico.buscar_llamadas(mascara, funciones.keys()):
        regla = funciones[funcion]
        args, _ = lexico.separar_argumentos(mascara, apertura)
        k = regla.get('arg', 0)
        if k >= len(args):
            continue
        a, b = args[k]
        spans = lexico.literales_del_argumento(mascara, literales, a, b)
        linea = lexico.numero_de_linea(src, inicio)
        if spans is None:
            if lexico.contiene_literal(literales, a, b):
                revisar.append((linea, funcion, src[a:b].strip()))
            continue
        if any(src[x - 2:x] in ('u8', 'L"') or src[x - 1] in 'uUL' for (x, _) in spans):
            revisar.append((linea, funcion, src[a:b].strip()))
            continue
        interior = nombres.contenido([src[x:y] for (x, y) in spans])
        tipo = regla['tipo']
        if tipo == 'id':
            ids.append((linea, funcion, (spans[0][0], spans[-1][1]), interior))
            continue
        original = interior
        sufijo = ''
        if tipo in ('etiqueta', 'titulo_con_id') and '##' in interior:
            corte = interior.index('##')
            interior, sufijo = interior[:corte], interior[corte:]
        visible = nombres.decodificar(interior)
        if nombres.letras(visible) < minimo or any(r.search(visible) for r in excluir):
            continue
        sin_args = (tipo == 'formato' and len(args) == k + 1)
        if sin_args:
            interior = interior.replace('%%', '%')
        hallazgos.append(Hallazgo(linea, funcion, tipo, (spans[0][0], spans[-1][1]),
                                  interior, sufijo, sin_args, original))
    # Un 'id' (OpenPopup...) solo cambia si nombra un titulo_con_id del mismo
    # archivo: pasa a usar el mismo ID fijo que el titulo traducido.
    titulos = {h.original for h in hallazgos if h.tipo == 'titulo_con_id'}
    for linea, funcion, span, interior in ids:
        if interior in titulos:
            h = Hallazgo(linea, funcion, 'id', span, interior, '', False, interior)
            h.nombre = '-'
            hallazgos.append(h)
    return src, hallazgos, revisar


def asignar_nombres(hallazgos, textos, cfg, nuevos):
    usados = set(textos.nombres()) | {n for (n, _) in nuevos}
    for h in hallazgos:
        if h.tipo == 'id':
            continue
        existente = textos.nombre_por_interior(h.interior)
        if existente is None:
            existente = next((n for (n, t) in nuevos if t == h.interior), None)
        if existente:
            h.nombre = existente
            continue
        base = nombres.nombre_para(nombres.decodificar(h.interior), cfg.get('max_palabras_nombre', 5))
        nombre, k = base, 2
        while nombre in usados:
            nombre, k = '%s%d' % (base, k), k + 1
        usados.add(nombre)
        nuevos.append((nombre, h.interior))
        h.nombre = nombre


def expresion(h, cfg):
    p = cfg['plantillas']
    if h.tipo == 'etiqueta':
        plantilla = p['etiqueta_con_sufijo'] if h.sufijo else p['etiqueta']
    elif h.tipo in ('titulo_con_id', 'id'):
        plantilla = p[h.tipo]
    elif h.tipo == 'formato' and h.sin_args:
        plantilla = p['formato_sin_argumentos']
    else:
        plantilla = p[h.tipo]
    return (plantilla.replace('{nombre}', h.nombre).replace('{sufijo}', h.sufijo)
            .replace('{original}', h.original))


def asegurar_include(src, ruta, cfg):
    cabecera = cfg.get('cabecera')
    agregado = []
    if cabecera:
        rel = os.path.relpath(os.path.abspath(cabecera), os.path.dirname(os.path.abspath(ruta)))
        rel = rel.replace(os.sep, '/')
        if os.path.basename(cabecera) not in src:
            agregado.append('#include "%s"' % rel)
    declaracion = cfg.get('declaracion')
    if declaracion and declaracion not in src:
        agregado.append(declaracion)
    if not agregado:
        return src
    includes = list(re.finditer(r'^#include [<"][^>"]+[>"][^\n]*\n', src, re.M))
    pos = includes[-1].end() if includes else 0
    bloque = ''.join(x + '\n' for x in agregado if x.startswith('#include'))
    if declaracion in agregado:
        bloque += '\n' + declaracion + '\n'
    return src[:pos] + bloque + src[pos:]


def literales_en_otros(raiz, interiores, procesados):
    """Literales de popup/etiqueta que siguen escritos tal cual en otros archivos."""
    avisos = []
    if not raiz:
        return avisos
    for base, _, archivos in os.walk(raiz):
        for a in archivos:
            ruta = os.path.join(base, a)
            if not a.endswith(('.cpp', '.h', '.hpp', '.cc')) or os.path.abspath(ruta) in procesados:
                continue
            src = open(ruta, encoding='utf-8', errors='ignore').read()
            for t in interiores:
                if '"%s"' % t in src:
                    avisos.append('%s: el literal "%s" sigue escrito ahi' % (ruta, t))
    return avisos


def modo_extraer(args, cfg):
    textos = ArchivoTextos(cfg['archivo_textos'], cfg['textos'])
    nuevos = []
    resultados = []
    for ruta in args.archivos:
        src, hallazgos, revisar = analizar(ruta, cfg)
        asignar_nombres(hallazgos, textos, cfg, nuevos)
        resultados.append((ruta, src, hallazgos, revisar))
    total = 0
    for ruta, src, hallazgos, revisar in resultados:
        print('== %s: %d textos' % (ruta, sum(1 for h in hallazgos if h.tipo != 'id')))
        for h in hallazgos:
            print('  %4d %-26s %-24s "%s"%s' % (h.linea, h.funcion, h.nombre, h.interior,
                                                ('  [' + h.sufijo + ']') if h.sufijo else ''))
        for linea, funcion, texto in revisar:
            print('  %4d %-26s REVISAR A MANO: %s' % (linea, funcion, texto))
        total += sum(1 for h in hallazgos if h.tipo != 'id')
    print('Total: %d textos, %d nuevos en %s' % (total, len(nuevos), cfg['archivo_textos']))
    ids = {h.original for (_, _, hs, _) in resultados for h in hs
           if h.tipo in ('titulo_con_id', 'id')}
    procesados = {os.path.abspath(r) for r in args.archivos}
    for aviso in literales_en_otros(args.raiz, sorted(ids), procesados):
        print('AVISO (ID compartido):', aviso)
    if not args.aplicar:
        return 0
    for nombre, interior in nuevos:
        textos.agregar(nombre, interior)
    textos.escribir()
    for ruta, src, hallazgos, _ in resultados:
        if not hallazgos:
            continue
        for h in sorted(hallazgos, key=lambda x: x.span[0], reverse=True):
            a, b = h.span
            src = src[:a] + expresion(h, cfg) + src[b:]
        src = asegurar_include(src, ruta, cfg)
        open(ruta, 'w', encoding='utf-8').write(src)
    errores = ArchivoTextos(cfg['archivo_textos'], cfg['textos']).verificar()
    for e in errores:
        print('ERROR:', e)
    print('Aplicado.')
    return 1 if errores else 0


def modo_verificar(args, cfg):
    textos = ArchivoTextos(cfg['archivo_textos'], cfg['textos'])
    errores = textos.verificar()
    if args.raiz:
        tipo = cfg.get('tipo_texto', 'Texto')
        existentes = set(textos.nombres())
        patron = re.compile(r'\b' + re.escape(tipo) + r'::(\w+)')
        for base, _, archivos in os.walk(args.raiz):
            for a in archivos:
                if not a.endswith(('.cpp', '.h', '.hpp', '.cc')):
                    continue
                ruta = os.path.join(base, a)
                src = open(ruta, encoding='utf-8', errors='ignore').read()
                mascara, _ = lexico.escanear(src)
                # Las directivas (#define con parametros) no son usos reales.
                mascara = re.sub(r'^[ \t]*#.*$', '', mascara, flags=re.M)
                for m in patron.finditer(mascara):
                    if m.group(1) not in existentes:
                        errores.append('%s:%d usa %s::%s, que no existe' % (
                            ruta, lexico.numero_de_linea(src, m.start()), tipo, m.group(1)))
    for e in errores:
        print('ERROR:', e)
    n = len(textos.nombres())
    print('%d textos x %d idiomas: %s' % (n, len(textos.bloques), 'OK' if not errores else 'con errores'))
    for b in textos.bloques[1:]:
        pend = len(textos.pendientes(b.numero))
        if pend:
            print('  bloque %d: %d textos sin traducir (usan el del bloque 0)' % (b.numero, pend))
    return 1 if errores else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('archivos', nargs='*')
    ap.add_argument('--config', required=True)
    ap.add_argument('--aplicar', action='store_true')
    ap.add_argument('--pendientes', type=int)
    ap.add_argument('--traducciones')
    ap.add_argument('--bloque', type=int)
    ap.add_argument('--verificar', action='store_true')
    ap.add_argument('--raiz', help='carpeta de codigo para los avisos y la verificacion')
    args = ap.parse_args()
    cfg = cargar_config(args.config)
    if args.pendientes is not None:
        textos = ArchivoTextos(cfg['archivo_textos'], cfg['textos'])
        print(json.dumps(textos.pendientes(args.pendientes), ensure_ascii=False, indent=1))
        return 0
    if args.traducciones:
        if args.bloque is None:
            raise SystemExit('--traducciones necesita --bloque N')
        textos = ArchivoTextos(cfg['archivo_textos'], cfg['textos'])
        errores = textos.traducir(args.bloque, json.load(open(args.traducciones, encoding='utf-8')))
        for e in errores:
            print('ERROR:', e)
        textos.escribir()
        return modo_verificar(args, cfg) or (1 if errores else 0)
    if args.verificar:
        return modo_verificar(args, cfg)
    if not args.archivos:
        ap.error('faltan archivos')
    return modo_extraer(args, cfg)


if __name__ == '__main__':
    sys.exit(main())
