# SPDX-License-Identifier: Apache-2.0
"""Archivo de textos posicional: un bloque por idioma, mismas entradas y orden.

Formato (configurable con 'textos' en el JSON de configuracion):

    <inicio_bloque con el numero de idioma>     p. ej. #if TEXTOS_BLOQUE < 0 || TEXTOS_BLOQUE == 1
    IDIOMA(...) u otras lineas (se conservan tal cual)
    PREFIJO(Nombre, "texto")
    PREFIJO(Nombre,
            "texto largo partido "
            "en varias lineas")
    <fin_bloque>                                p. ej. #endif

Las entradas nuevas se agregan al final de cada bloque (misma posicion en
todos). En los bloques que no son el 0 el texto queda vacio ("") hasta que
se cargue la traduccion.
"""
import re

from . import lexico, nombres


class Entrada:
    def __init__(self, nombre, literales, lineas_originales=None):
        self.nombre = nombre
        self.literales = literales          # fuente de cada literal, con comillas
        self.lineas = lineas_originales     # None si hay que regenerarla

    @property
    def interior(self):
        return nombres.contenido(self.literales)


class Bloque:
    def __init__(self, numero):
        self.numero = numero
        self.items = []                     # ('linea', str) o ('entrada', Entrada)

    def entradas(self):
        return [e for (t, e) in self.items if t == 'entrada']


class ArchivoTextos:
    def __init__(self, ruta, cfg):
        self.ruta = ruta
        self.prefijo = cfg.get('prefijo_entrada', 'TEXTO')
        self.re_inicio = re.compile(cfg['inicio_bloque'])
        self.re_fin = re.compile(cfg['fin_bloque'])
        self.ancho = cfg.get('ancho_maximo', 100)
        self.re_entrada = re.compile(r'^\s*' + re.escape(self.prefijo) + r'\(\s*(\w+)\s*,')
        self.cabecera = []
        self.bloques = []
        self.entre = []                     # lineas entre/tras bloques: [(despues_de_bloque, linea)]
        self._leer()

    def _leer(self):
        lineas = open(self.ruta, encoding='utf-8').read().split('\n')
        actual = None
        i = 0
        while i < len(lineas):
            linea = lineas[i]
            if actual is None:
                m = self.re_inicio.match(linea)
                if m:
                    actual = Bloque(int(m.group(1)))
                    actual.items.append(('linea', linea))
                    self.bloques.append(actual)
                elif not self.bloques:
                    self.cabecera.append(linea)
                else:
                    self.entre.append((len(self.bloques) - 1, linea))
                i += 1
                continue
            if self.re_fin.match(linea):
                actual.items.append(('linea', linea))
                actual = None
                i += 1
                continue
            m = self.re_entrada.match(linea)
            if not m:
                actual.items.append(('linea', linea))
                i += 1
                continue
            # La entrada sigue hasta cerrar el parentesis del prefijo.
            j = i
            trozo = linea
            while True:
                mascara, _ = lexico.escanear(trozo)
                if mascara.count('(') <= mascara.count(')'):
                    break
                j += 1
                trozo += '\n' + lineas[j]
            mascara, lits = lexico.escanear(trozo)
            literales = [trozo[a:b] for (a, b) in lits]
            actual.items.append(('entrada', Entrada(m.group(1), literales, lineas[i:j + 1])))
            i = j + 1

    # -- consultas -----------------------------------------------------------
    def base(self):
        return self.bloques[0]

    def nombres(self):
        return [e.nombre for e in self.base().entradas()]

    def nombre_por_interior(self, interior):
        for e in self.base().entradas():
            if e.interior == interior:
                return e.nombre
        return None

    def pendientes(self, numero):
        bloque = self._bloque(numero)
        base = {e.nombre: e.interior for e in self.base().entradas()}
        # Texto legible (sin escapes de C), el mismo formato que espera traducir().
        return {e.nombre: nombres.decodificar(base.get(e.nombre, ''))
                for e in bloque.entradas() if e.interior == ''}

    def _bloque(self, numero):
        for b in self.bloques:
            if b.numero == numero:
                return b
        raise SystemExit('no hay bloque de idioma %d en %s' % (numero, self.ruta))

    # -- cambios -------------------------------------------------------------
    def agregar(self, nombre, interior_base):
        for b in self.bloques:
            texto = '"%s"' % interior_base if b is self.bloques[0] else '""'
            entrada = Entrada(nombre, [texto])
            # antes de la linea de cierre del bloque
            b.items.insert(len(b.items) - 1, ('entrada', entrada))

    def quitar(self, nombre):
        for b in self.bloques:
            b.items = [(t, x) for (t, x) in b.items if not (t == 'entrada' and x.nombre == nombre)]

    def traducir(self, numero, traducciones):
        """Carga textos en el bloque 'numero'. Devuelve la lista de errores."""
        errores = []
        bloque = self._bloque(numero)
        base = {e.nombre: e.interior for e in self.base().entradas()}
        por_nombre = {e.nombre: e for e in bloque.entradas()}
        for nombre, texto in traducciones.items():
            if nombre not in por_nombre:
                errores.append('%s: no existe en el bloque %d' % (nombre, numero))
                continue
            interior = texto.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            if nombres.especificadores(interior) != nombres.especificadores(base[nombre]):
                errores.append('%s: los %% del formato no coinciden con el bloque 0' % nombre)
                continue
            e = por_nombre[nombre]
            e.literales = ['"%s"' % interior]
            e.lineas = None
        return errores

    # -- escritura -----------------------------------------------------------
    def _formatear(self, e):
        if e.lineas is not None:
            return e.lineas
        interior = e.interior
        una = '%s(%s, "%s")' % (self.prefijo, e.nombre, interior)
        if len(una) <= self.ancho:
            return [una]
        sangria = ' ' * (len(self.prefijo) + 1)
        trozos = partir(interior, self.ancho - len(sangria) - 3)
        lineas = ['%s(%s,' % (self.prefijo, e.nombre)]
        for k, t in enumerate(trozos):
            cierre = ')' if k == len(trozos) - 1 else ''
            lineas.append('%s"%s"%s' % (sangria, t, cierre))
        return lineas

    def escribir(self):
        out = list(self.cabecera)
        for k, b in enumerate(self.bloques):
            for tipo, x in b.items:
                out.extend(self._formatear(x) if tipo == 'entrada' else [x])
            out.extend(l for (despues, l) in self.entre if despues == k)
        open(self.ruta, 'w', encoding='utf-8').write('\n'.join(out))

    # -- verificacion --------------------------------------------------------
    def verificar(self):
        errores = []
        numeros = [b.numero for b in self.bloques]
        if numeros != list(range(len(numeros))):
            errores.append('los bloques no estan numerados 0, 1, 2... en orden: %s' % numeros)
        base = self.nombres()
        if len(set(base)) != len(base):
            vistos = set()
            dup = sorted({n for n in base if n in vistos or vistos.add(n)})
            errores.append('nombres repetidos en el bloque 0: %s' % ', '.join(dup))
        formatos = {e.nombre: nombres.especificadores(e.interior) for e in self.base().entradas()}
        for b in self.bloques[1:]:
            otros = [e.nombre for e in b.entradas()]
            if otros != base:
                errores.append('el bloque %d no tiene las mismas entradas en el mismo orden' % b.numero)
            for e in b.entradas():
                if e.interior and nombres.especificadores(e.interior) != formatos.get(e.nombre):
                    errores.append('bloque %d, %s: los %% no coinciden con el bloque 0' % (b.numero, e.nombre))
        return errores


def partir(interior, ancho):
    """Parte el interior de un literal en trozos de a lo sumo 'ancho', en espacios."""
    trozos = []
    while len(interior) > ancho:
        corte = interior.rfind(' ', 0, ancho)
        if corte <= 0:
            corte = ancho
            while corte < len(interior) and interior[corte - 1] == '\\':
                corte += 1
        else:
            corte += 1
        trozos.append(interior[:corte])
        interior = interior[corte:]
    trozos.append(interior)
    return trozos
