# Traductor de Lua a Python 3

**Autor:** Arnold Oswaldo Acosta Ortega

Traductor de programas escritos en **Lua a Python 3**, desarrollado en Python mediante ANTLR 4.13.2. Implementa análisis léxico, sintáctico y semántico, junto con un mecanismo de traducción que genera código Python equivalente, listo para ejecutarse.

El programa recibe código Lua mediante la entrada estándar y genera el código Python correspondiente por la salida estándar. También permite traducir y ejecutar programas directamente, sin necesidad de generar un archivo intermedio.

## Trabajo desarrollado

Se desarrolló un traductor de Lua a Python 3, implementado en Python 3 con ANTLR 4.13.2 (target Python3). Su funcionamiento se organiza en tres componentes principales:

1. **Análisis léxico y sintáctico:** generados por ANTLR a partir de la gramática de Lua disponible en el repositorio [`antlr/grammars-v4`](https://github.com/antlr/grammars-v4), específicamente en la carpeta `lua/`, distribuida bajo licencia MIT. Para adaptar las gramáticas al target de Python se realizaron dos ajustes: los predicados semánticos `this.` se reemplazaron por `self.` y se incorporaron las clases base `LuaLexerBase.py` y `LuaParserBase.py` de `lua/Python3/`.

2. **Traducción:** implementada mediante un *Visitor* de ANTLR en `traductor.py`. La clase `LuaToPython` recorre el árbol sintáctico y transforma las construcciones reconocidas del lenguaje Lua en código Python.

3. **Runtime de compatibilidad:** implementado en `lua_runtime.py`, contiene funciones y clases que reproducen características semánticas de Lua que Python no ofrece de forma nativa, como tablas, `nil`, evaluación de valores de verdad, operaciones aritméticas con enteros de 64 bits, metatablas, corrutinas, patrones de cadenas y bibliotecas estándar.

La salida del traductor es autónoma: `main.py` incorpora el contenido de `lua_runtime.py` al código traducido. De esta manera, el resultado puede ejecutarse utilizando únicamente Python 3, sin depender de los archivos originales del proyecto durante su ejecución.

## Estructura del proyecto

```text
.
├── main.py               # Punto de entrada: stdin (Lua) -> stdout (Python)
├── traductor.py          # Visitor que traduce el árbol sintáctico
├── lua_runtime.py        # Runtime que acompaña al código traducido
├── LuaLexer.g4           # Gramática fuente del lexer
├── LuaParser.g4          # Gramática fuente del parser
├── LuaLexer.py           # Lexer generado por ANTLR
├── LuaParser.py          # Parser generado por ANTLR
├── LuaParserVisitor.py   # Visitor generado por ANTLR
├── LuaLexerBase.py       # Clase base del lexer
├── LuaParserBase.py      # Clase base del parser
├── antlr4/               # Runtime de ANTLR 4.13.2 para Python
└── README.md
```

## Requisitos

- Python 3.8 o superior. El código generado utiliza el operador de asignación `:=`.
- Para ejecutar el traductor no se requiere instalar dependencias adicionales: el runtime de ANTLR está incluido en el directorio `antlr4/`.
- Para regenerar el lexer y el parser se necesita Java JRE/JDK y el archivo `antlr-4.13.2-complete.jar`.

## Cómo ejecutar el traductor

El programa admite dos modalidades de ejecución.

### 1. Modo traductor

Es el modo predeterminado. El programa Lua se proporciona mediante la entrada estándar y el código Python resultante se escribe en la salida estándar.

**Generar un archivo Python:**

```bash
python3 main.py < programa.lua > salida.py
```

**Ejecutar el resultado:**

```bash
python3 salida.py
```

**Traducir y ejecutar en una sola línea:**

```bash
python3 main.py < programa.lua | python3
```

### 2. Modo de ejecución directa

Mediante la opción `--run` o `-r`, `main.py` traduce y ejecuta el programa en el mismo proceso, sin generar un archivo intermedio.

**Leer el programa desde un archivo:**

```bash
python3 main.py --run programa.lua
```

**Leer el programa desde la entrada estándar:**

```bash
python3 main.py --run < programa.lua
```

Cuando el archivo se proporciona como argumento, la entrada estándar queda disponible para que el programa Lua pueda leer datos mediante `io.read`.

Si el programa termina con un error no capturado, se muestra un mensaje con el formato `lua: mensaje` en la salida de error y el proceso finaliza con código de salida `1`, siguiendo el comportamiento del intérprete de Lua.

### Ejemplo de ejecución

Archivo `hola.lua`:

```lua
local function saludar(nombre)
    return "hola " .. nombre
end

print(saludar("mundo"))
```

Ejecución:

```bash
python3 main.py --run hola.lua
```

Salida:

```text
hola mundo
```

### Manejo de características no soportadas

Cuando el traductor encuentra una construcción que todavía no está implementada, finaliza con código de salida `1` y muestra un mensaje descriptivo en la salida de error:

```text
No soportado todavía: ...
```

Esto permite identificar las características que requieren implementación adicional sin producir silenciosamente una traducción incorrecta.

## Regeneración del lexer y el parser

Este procedimiento solo es necesario cuando se modifican los archivos de gramática.

### 1. Obtener las gramáticas

Descargar `LuaLexer.g4` y `LuaParser.g4` desde el repositorio [`antlr/grammars-v4`](https://github.com/antlr/grammars-v4), dentro de la carpeta `lua/`.

También se deben obtener los archivos `LuaLexerBase.py` y `LuaParserBase.py`, disponibles en `lua/Python3/`.

### 2. Adaptar las gramáticas al target de Python

Reemplazar las referencias `this.` por `self.`:

```bash
sed -i 's/this\./self./g' LuaLexer.g4 LuaParser.g4
```

### 3. Generar el código Python

Utilizar ANTLR 4.13.2 para generar el lexer, el parser y el Visitor:

```bash
java -jar antlr-4.13.2-complete.jar \
    -Dlanguage=Python3 \
    -visitor \
    -no-listener \
    LuaLexer.g4 LuaParser.g4
```

Es importante utilizar la misma versión de ANTLR que la del runtime incluido en el proyecto para mantener la compatibilidad.

### 4. Instalar el runtime dentro del proyecto

Si es necesario preparar nuevamente el runtime local:

```bash
pip install --target . antlr4-python3-runtime==4.13.2
```

La instalación local permite mantener la dependencia dentro del proyecto, sin requerir una instalación global.

## Versión de Lua y compatibilidad

La gramática de ANTLR utilizada cubre la sintaxis hasta **Lua 5.4**, incluidos los atributos `<const>` y `<close>`.

El comportamiento del traductor y su runtime se verificó mediante comparaciones con los intérpretes oficiales `lua5.4` y `lua5.5`. Cuando existen diferencias entre ambas versiones, el runtime sigue el comportamiento de Lua 5.5 en los aspectos contemplados.

Entre estas diferencias se encuentran:

- La representación de números flotantes utiliza 14 dígitos y, cuando es necesario para reconstruir el valor, hasta 17 dígitos. Por ejemplo, `3.1416` y `3.3333333333333335`.
- Los errores cuyo valor asociado es `nil` se informan como `<no error object>`.
- Las declaraciones `global` introducidas en Lua 5.5 todavía no están soportadas.

Por tanto, aunque se toma Lua 5.5 como referencia para determinados comportamientos del runtime, la gramática actual no reconoce toda su sintaxis.

## Características que se traducen

El traductor contempla las siguientes construcciones y mecanismos del lenguaje Lua:

| Característica de Lua | Implementación en Python |
|---|---|
| `local`, asignación múltiple, valores múltiples, `...`, `select` | Asignaciones y tuplas. |
| `if`, `while`, `repeat-until`, `for` numérico y genérico | `if/elif/else`, `while` y `for`. |
| `goto` y etiquetas | `continue` para patrones habituales; en otros casos, máquina de estados con excepciones. |
| Funciones, closures, funciones anónimas y recursión | `def`, con declaraciones `nonlocal` y `global` automáticas. |
| Variables `<close>` y `<const>` | `try/finally` con `__close`. |
| Tablas `{...}`, `t.x`, `t[i]`, `#t` | Clase `LuaTable`, con arreglo de base 1 y almacenamiento hash. |
| Metatablas y metamétodos | `setmetatable` y funciones `lua_*`. |
| Operadores aritméticos, bit a bit, `//`, `%`, `^`, `..` | Funciones como `lua_add`, `lua_band`, entre otras; enteros de 64 bits y coerción de cadenas. |
| Literales y cadenas | Escapes (`\x`, `\ddd`, `\u{}`, `\z`), cadenas largas, números hexadecimales y flotantes hexadecimales. |
| Corrutinas (`coroutine.*`) | Implementación mediante hilos de Python. |
| Bibliotecas `string`, `table`, `math`, `os`, `io`, `utf8` | Funciones y tablas del runtime. |
| `pcall`, `xpcall`, `error`, `assert` | Manejo de errores con mensajes `chunk:línea:` como Lua. |
| Variables globales no definidas | Se interpretan como `nil`. |
| Ámbito de bloque (`local x = x` y variables que ocultan a otras) | Nombres Python diferenciados (`x`, `x_2`, etc.); cierres en bucles con una variable propia por iteración. |
| `load` con cadenas de código Lua | Traducción y ejecución del código Lua admitido mediante `exec`. |
| Tablas débiles (`__mode`) y `collectgarbage` | Limpieza de entradas sin otras referencias. |
| `_ENV`, `_G`, `_VERSION` | Representación mediante la tabla de globales del programa. |

### Decisiones de compatibilidad semántica

Para conservar el comportamiento de Lua durante la ejecución del código traducido, se implementan reglas específicas que difieren de las convenciones de Python:

| Comportamiento de Lua | Regla aplicada |
|---|---|
| Valores falsos | Solamente `nil` y `false` se consideran falsos. |
| Cero y cadenas vacías | `0` y `""` se consideran verdaderos. |
| División `/` | Siempre produce un resultado de tipo `float`. |
| Potencia `^` | Siempre produce un resultado de tipo `float`. |
| Índices de tablas | Los arreglos comienzan en el índice 1. |
| Argumentos faltantes | Se completan automáticamente con `nil`. |
| Argumentos sobrantes | Se ignoran cuando la función recibe más argumentos de los esperados. |
| Cadenas | Se tratan como secuencias de bytes. |

Estas decisiones permiten conservar diferencias importantes entre ambos lenguajes y reducir cambios de comportamiento durante la traducción.

## Limitaciones conocidas

Aunque el traductor cubre una parte amplia de las características de Lua, existen funcionalidades y casos particulares que todavía presentan limitaciones:

- **Declaraciones `global` de Lua 5.5:** la gramática actual no las reconoce.
- **`load`:** admite código Lua válido proporcionado como cadena literal y, cuando el traductor se encuentra junto al programa generado, también cadenas construidas durante la ejecución. No se soportan `dofile` ni `require`.
- **Longitud de tablas con huecos:** el operador `#` devuelve el primer borde en los casos observados en Lua 5.5; otros casos con huecos pueden diferir del intérprete.
- **Mensajes de error aritméticos:** no incluyen el nombre de la variable, por ejemplo `(local 'x')`. Los errores de llamada e indexación sí pueden incluirlo cuando es inequívoco.
- **Nombre de los chunks:** cuando el programa se proporciona mediante la entrada estándar, los mensajes de error utilizan `input` por defecto.
- **Funciones no implementadas:** no se incluyen `string.pack`, `string.unpack` ni el metamétodo `__gc`.
- **Corrutinas:** su implementación mediante hilos de Python es una aproximación y no garantiza reproducir todas las características del modelo de corrutinas de Lua.

## Pruebas

El proyecto incluye la carpeta `pruebas/`, que contiene programas Lua utilizados para comprobar el comportamiento del traductor mediante comparaciones con el intérprete oficial `lua5.4`.

Para repetir una comparación de resultados:

```bash
python3 main.py programa.lua < programa.lua | python3 > obtenido.txt
lua5.4 programa.lua > esperado.txt
diff esperado.txt obtenido.txt
```

Este procedimiento permite contrastar la salida estándar del programa traducido con la del intérprete de referencia.

**Nota:** la comparación anterior evalúa la salida estándar. Los mensajes de error y los códigos de salida deben comprobarse por separado cuando se quieran validar esos comportamientos.

## Créditos y referencias

- **ANTLR grammars-v4:** gramáticas de Lua y clases base adaptadas para Python. [Repositorio oficial](https://github.com/antlr/grammars-v4). Licencia MIT para los componentes correspondientes.
- **ANTLR:** herramienta utilizada para generar el lexer, parser y Visitor. [Sitio oficial](https://www.antlr.org).
- **ANTLR Python Runtime:** runtime de ANTLR 4.13.2 incluido en el proyecto.

---

Desarrollado como proyecto académico para explorar el diseño e implementación de traductores, el análisis de lenguajes de programación y la compatibilidad semántica entre Lua y Python 3.
