# Inventario vinculado Panda / ADB / AGX

Comprobación real: **2026-11-02, America/Guatemala**. Se consultó únicamente el
inventario de Panda y propiedades de Android, sin capturas, gestos ni OpenAI.

- 34 entradas en la API Panda y 34 rutas ADB autorizadas.
- Dos servidores ADB consultados, sin errores de servidor.
- 34 identidades físicas verificadas, sin conflictos.
- 34 vínculos con el histórico AGX por serial exacto.
- 10.831 registros históricos, 38 identidades/alias históricos y cero
  interacciones conservados sin variación al comparar el respaldo previo.

La ficha visual 01 aparece desconectada en la captura aportada y no está en
la lista viva de Panda. No se inventó una correspondencia de hardware para
ella. Los saltos entre números no representan placas faltantes ni autorizan
crear dispositivos. La captura muestra fichas guardadas, no solo conectadas.

## Repetir la comprobación

Solo consultar, verificar seriales físicos y exportar un informe privado:

```powershell
.\.venv\Scripts\python.exe scripts/sincronizar_inventario_panda.py
```

Para guardar los vínculos en la SQLite principal del framework:

```powershell
.\.venv\Scripts\python.exe scripts/sincronizar_inventario_panda.py --apply
```

Antes de aplicar, se genera un respaldo SQLite consistente en el directorio
privado de la ejecución. El inventario CSV y el JSON quedan bajo
`runs/inventario-panda-<id>/`, excluidos de Git. No se modifican las bases fuente
del proyecto AGX ni se borran las fichas históricas del framework.

## Criterios y persistencia

Se leen `ro.serialno` y `ro.boot.serialno` en cada ruta ADB fijando su servidor.
Se rechazan emuladores, seriales inválidos, discrepancias y duplicados. El
número visual y el transporte IP:puerto no sustituyen al serial físico.
Solo se vincula cuando transporte, serial Panda y lectura Android coinciden
y el número visual y la identidad son unívocos. Un nombre parecido no basta.

La tabla `dispositivos` mantiene sus claves físicas, estados de cuenta y alias.
Se añaden `panda_numero`, `panda_nombre`, `panda_verificado_en` y `panda_estado`.
`panda_inventario_observaciones` conserva las correspondencias por ejecución;
no contiene capturas ni contraseñas. La interfaz Streamlit que consulta el
inventario puede mostrar estas columnas nuevas. Los nombres e identificadores
reales permanecen en SQLite y en los informes locales privados.

El inventario es una observación fechada: no acredita autenticación en TikTok,
salida de red, disponibilidad futura ni que una orden física se haya realizado.
