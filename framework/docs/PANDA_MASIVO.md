# QA masivo desde inventario CSV

Entrega verificada el 2026-11-02: 338 pruebas aprobadas. Preflight real con el
CSV local: 34 placas cargadas, 34 vinculos fisicos actuales y 34 admitidas, sin
exclusiones. No se ejecutaron capturas, swipes ni Vision real en esa validacion.

`main_panda_masivo.py` carga el inventario privado ya verificado. No contiene
llamadas simuladas ni rutas HTTP inventadas: reutiliza la API WebSocket local
de Panda y el pipeline de `main_panda.py`.

Reconoce tanto `Numero_Panda, serial, alias, transporte` como los encabezados
reales `numero_panda, serial_fisico, alias_agx, nombre_panda, transporte, estado`.
Admite BOM UTF-8. Excluye 01, serial vacio y filas no vinculadas. Numeros o
seriales duplicados abortan la carga. El valor esperado es 34 placas, ajustable
explicitamente mediante `--expected-count` para otro inventario de laboratorio.

## Preflight sin capturas ni OpenAI

```powershell
.\.venv\Scripts\python.exe main_panda_masivo.py
```

Por defecto lee el CSV privado generado en la ejecucion de inventario del
2026-11-02 indicada en el codigo. Para otra PC o un inventario mas reciente,
usar `--inventory RUTA_CSV`. Debe regenerarse el inventario en esa PC; el archivo
con nombres y seriales reales no viaja en Git.

El preflight vuelve a leer propiedades fisicas de Android y Panda. Las placas
que ya no coinciden quedan fuera del lote. El adaptador fija el serial esperado
y lo revalida durante la captura y antes del swipe. Una IP nueva no autoriza
cambiar el vinculo historico. Se informan cantidades, no alias o credenciales.

## Ejecucion autorizada de QA

Tras revisar manualmente las placas en el feed de prueba:

```powershell
.\.venv\Scripts\python.exe main_panda_masivo.py --execute-read-only --ready --cycles 5 --concurrency 5 --rpm 30
```

Sin `--allow-vision-upload` solo captura y desplaza; no envia imagenes a OpenAI.
Para incluir analisis visual, agregar ese flag: autoriza transmitir capturas
completas. El modelo predeterminado es `gpt-4o-mini`, como en el esqueleto
solicitado; `--vision-model gpt-4o` permite el modelo del flujo anterior.
La API key se carga de `.env` y el cliente se crea y cierra dentro del worker.
No hay clientes SDK inicializados al importar el modulo.

El semaforo admite como maximo cinco consultas de vision activas. Adicionalmente
el gate limita el inicio de solicitudes a `--rpm` por minuto, compartido por el
lote. Esto no garantiza un limite TPM: imagenes y respuestas consumen tokens
variables y siguen sujetos a la cuota del proyecto OpenAI. Los errores de cuota
se registran sin reintentos automaticos ni afectar a las otras placas. La pausa
de reproduccion QA es determinista, configurable entre 8 y 22 segundos y cancelable.

## Persistencia

La SQLite privada `telemetria_panda.db` conserva `auditorias_panda` e incorpora
serial y alias, sin borrar filas antiguas. La vista `logs_panda_farm` expone
timestamp, panda_id, serial, alias y analisis_vision, ademas del run y estado.
No se duplica el contenido en otra tabla. El lote se confirma atomicamente antes
del swipe; tambien se actualiza su resultado al recibir confirmacion o incertidumbre.

Los fallos y cancelaciones conservan la identidad del CSV. Capturas e informes
contienen datos privados y siguen excluidos de Git. Las tablas QA separadas solo
guardan metricas y codigos. Los logs de este comando se normalizan a ASCII y no
imprimen el contenido visual. No se publican likes ni comentarios. Una orden de
swipe aceptada no acredita que el video haya cambiado.
