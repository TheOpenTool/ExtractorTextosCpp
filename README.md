# ExtractorTextosCpp

Pasa los textos visibles de un código C++ (etiquetas de botones, menús,
títulos, ayudas...) a **un solo archivo de textos posicional** y reemplaza cada
literal por una expresión que lo busca en ese archivo según el idioma.

Nació para FunshiEngineOpenGL (editor con ImGui), pero no tiene nada del motor
adentro: las funciones a revisar, las expresiones de reemplazo y el formato del
archivo de textos entran por un JSON de configuración.

## Formato posicional

El archivo de textos tiene un bloque por idioma, numerados en orden (0, 1, 2…).
Todos los bloques tienen las mismas N entradas en el mismo orden, así que el
texto `i` del idioma `n` está en la posición `n * N + i`:

```
#if TEXTOS_BLOQUE < 0 || TEXTOS_BLOQUE == 0
IDIOMA(0, "es", "Espanol")
TEXTO(Guardar, "Guardar")
TEXTO(Salir, "Salir")
#endif
#if TEXTOS_BLOQUE < 0 || TEXTOS_BLOQUE == 1
IDIOMA(1, "en", "English")
TEXTO(Guardar, "Save")
TEXTO(Salir, "Exit")
#endif
```

El nombre de cada entrada (`Guardar`) es lo que usa el código (`Texto::Guardar`);
el código del proyecto decide cómo se compila ese archivo (en FunshiEngine es un
X-macro con `static_assert` que comprueban bloques alineados).

## Requisitos

- Python 3.8+ (sin dependencias)

## Uso rápido

```bash
# Ver qué textos saldrían de esos archivos y con qué nombre (no escribe nada)
python3 extraer_textos.py --config cfg.json src/Gui/Menu.cpp src/Gui/Barra.cpp

# Aplicar: agrega los textos nuevos (bloque 0 con el texto, el resto vacíos)
# y reemplaza los literales. --raiz avisa si un ID de popup sigue escrito en
# otro archivo que no se procesó.
python3 extraer_textos.py --config cfg.json src/Gui/*.cpp --aplicar --raiz src

# Lo que falta traducir en el bloque 1, como JSON {nombre: texto del bloque 0}
python3 extraer_textos.py --config cfg.json --pendientes 1 > pendientes.json

# Cargar las traducciones (JSON {nombre: texto}) en el bloque 1
python3 extraer_textos.py --config cfg.json --traducciones en.json --bloque 1

# Comprobar el archivo de textos y que todo Texto::X del código exista
python3 extraer_textos.py --config cfg.json --verificar --raiz src
```

## Configuración

Ver `ejemplos/config_imgui.json`. Claves:

| Clave | Qué es |
|-------|--------|
| `archivo_textos` | Ruta del archivo de textos posicional |
| `cabecera` | Header a incluir en los archivos modificados (ruta relativa calculada sola) |
| `declaracion` | Línea a agregar tras los includes si falta (p. ej. `using Loc::Texto;`) |
| `tipo_texto` | Nombre del enum de textos, para `--verificar` |
| `minimo_letras` | Un literal con menos letras visibles no se extrae (`"X"`, `"%d"`, `"##id"`) |
| `excluir` | Regex de textos visibles que no se extraen |
| `max_palabras_nombre` | Palabras del texto que forman el nombre de la entrada |
| `textos` | Formato del archivo: `prefijo_entrada`, regex `inicio_bloque` (grupo 1 = número), regex `fin_bloque`, `ancho_maximo` |
| `funciones` | Función → `{"tipo": ..., "arg": índice}` (arg 0 por defecto) |
| `plantillas` | Expresión de reemplazo por tipo; `{nombre}`, `{sufijo}`, `{original}` |

Tipos de función:

| Tipo | Uso | Reemplazo |
|------|-----|-----------|
| `texto` | texto que se muestra tal cual | `plantillas.texto` |
| `formato` | cadena de formato printf; sin más argumentos usa `formato_sin_argumentos` (y `%%` pasa a `%`) | `plantillas.formato` |
| `etiqueta` | etiqueta de widget; un `##id` del literal se conserva como sufijo | `etiqueta` / `etiqueta_con_sufijo` |
| `titulo_con_id` | título visible que también es ID (modales de ImGui): se traduce y el ID queda fijo en `###<original>` | `titulo_con_id` |
| `id` | ID puro (`OpenPopup`): solo cambia si nombra un `titulo_con_id` del mismo archivo, para seguir abriendo el mismo popup | `id` |

## Qué garantiza

- Solo toca argumentos que son **únicamente** literales de cadena (uno o varios
  seguidos), fuera de comentarios y de otras cadenas.
- Un texto que ya existe en el bloque 0 se reutiliza (mismo nombre).
- Nombres únicos (sufijo numérico si dos textos distintos dan el mismo nombre).
- `--traducciones` rechaza un texto cuyos especificadores `%` no coinciden con
  los del bloque 0.
- `--verificar`: bloques numerados en orden, mismas entradas y mismo orden en
  todos, nombres únicos, `%` iguales y, con `--raiz`, ningún `Texto::X`
  inexistente en el código.

## Límites

- Un argumento mezclado (`cond ? "A" : "B"`, `"A" + x`, arrays de ítems) no se
  toca: se lista como `REVISAR A MANO`.
- Literales con prefijo (`u8"..."`, `L"..."`) y crudos (`R"(...)"`) no se extraen.
- Títulos de ventana (`Begin`) no están en el ejemplo: su nombre suele ser
  también el ID del dock y del `.ini` de layout; conviene tratarlos aparte.
- No traduce: deja los bloques ≠ 0 vacíos y el proyecto decide qué mostrar
  mientras tanto (en FunshiEngine, el texto del bloque 0).
- Siempre compilar y correr los tests del proyecto después de aplicar.

## Licencia

Apache 2.0 (ver `LICENSE`).
