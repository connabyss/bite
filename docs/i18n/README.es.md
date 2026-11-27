# Bite (Español)

[English](../../README.md) · [Tiếng Việt](README.vi.md) · **Español** · [简体中文](README.zh-CN.md)

> Esta traducción corta se hizo con ayuda de IA. Si algo no suena bien, abre un issue o un pull request. La versión en inglés es la completa y la más reciente.

### ¿Tus tests lo notarían si el bug volviera?

Bite comprueba si el "arreglado" de un agente de IA que programa es verdad.
Quita cada arreglo de una copia de tu proyecto y ejecuta tus tests. Gratis, sin clave.

## Pruébalo ahora

Gratis, sin clave, y nunca cambia tus archivos. Necesitas Python 3.10 o más nuevo y git. Pega estas dos líneas en
cualquier terminal (PowerShell, cmd, Terminal):

```
python -m pip install bite-check
python -m bite_check --free
```

Fuera de un proyecto, Bite primero muestra una demo en un proyecto pequeño inventado. Para revisar tu propio proyecto, escribe la
segunda línea y un espacio, arrastra la carpeta de tu proyecto a la ventana (eso escribe su ruta) y pulsa Enter.

## Por qué lo necesitas

Cuando una IA te arregla un bug, muchas veces dice: "Arreglado, y añadí un test." Si no lees código, no puedes saber
si es verdad.

Un test es un robot pequeño que revisa una cosa y grita cuando algo está mal. Bite vuelve a poner el bug viejo a propósito
y mira si algún test grita. Es como probar una alarma de humo con humo de verdad en vez de fiarte de la lucecita verde.

Si un test grita, ese arreglo está protegido. Si todos se quedan callados, el bug podría volver y nadie se daría cuenta.
Bite nombra ese arreglo para que le puedas decir a tu IA: "añade un test que falle sin este arreglo."

## Cómo leer el resultado

- ✅ **noticed by** (lo notó) el nombre de un test: ese test protege el arreglo.
- ⚠️ **NO TEST NOTICED** (ningún test lo notó): sin el arreglo, todos los tests siguen pasando. El bug podría volver sin que nadie lo note.

Cada ejecución deja una página de informe, `bite_proof/report.html`, para abrir en el navegador.

## Más información

Todo lo demás (la GitHub Action, la revisión en vivo en Claude Code, el paso de pago con tu propia clave de API) está en el
[README en inglés](../../README.md) y en la [guía de instalación](../install.md).
