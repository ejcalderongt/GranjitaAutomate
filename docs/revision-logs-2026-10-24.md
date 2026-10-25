# Revisión de logs y mejoras · 2026-10-24

Fecha America/Guatemala. Versión de mejora: 2.12. Fuentes: traces.sqlite3 y automation.sqlite3 leídas sin instanciar JobStore para el análisis, evitando alterar estados al consultar. Ventana analizada: registros desde 18:45 hasta aproximadamente 18:57 GT. Los conteos son históricos, no una nueva medición de conectividad física.

## Resultados confirmados

| Evidencia | Resultado | Interpretación |
| --- | --- | --- |
| Lote de 28 placas, receta de tres tarjetas | 26 tareas Completado; 2 Revisar resultado | No declarar éxito total del lote. |
| Auditoría por destino de ese lote | 84 planeados, 83 iniciados, 81 verificados: 76 aplicados y 5 ya marcados | Dos sin confirmar y uno no iniciado; conservarlos fuera de likes nuevos. |
| Dos tareas incompletas | Falta de elemento después de observed y click_requested en tarjetas 03 y 02 | No prueba que el clic haya sido enviado ni que haya fallado el hardware. No se reejecutaron esas tareas. |
| Inicio con snapshots | 28 Verificado, total 59.8 s; mediana por placa 2.21 s | La pasada es secuencial; el inventario completo ocupa aproximadamente 1.87 s por placa. |
| Búsqueda de dispositivos | Mediana aproximada 3.4 s en las primeras seis muestras | Hay costo fijo de descubrimiento Windows cercano a 2 s. |
| Errores finos operativos anteriores | Tres eventos adb.list sobre puertos altos, dos timeout y un cierre de conexión | Son consultas al protocolo local, no tres placas fallidas; podrían ser listeners de transporte/forward en lugar de servidores host ADB. Falta verificar el rol exacto de esos puertos. |
| Apertura Appium | Tres muestras cercanas a 5.3 s | Costo relevante, pero no todo proviene de instalar APK. |

Se cruzó el lote anterior a la instrumentación fina con su auditoría existente. Las trazas nuevas por sí solas no contienen la causa completa de aquellos dos fallos; el diagnóstico de sincronización es una hipótesis respaldada por el orden de eventos y el código, no una causa física confirmada.

## Mejora aplicada en 2.12

El flujo volvía a buscar el mismo botón para leer, pulsar y verificar, después de desplazar el feed. Ahora reutiliza el identificador devuelto al localizar la tarjeta, espera dos lecturas consecutivas de su rectángulo iguales y verifica que esté habilitado antes de leer/pulsar. Espera acotada a cinco segundos, revisando cancelación y horario. Si no se estabiliza, no envía clic.

La pulsación usa esa referencia; la verificación posterior puede recuperar una referencia recreada por Android solo para LEER el estado. Nunca reenvía el clic por incertidumbre. Si la verificación no confirma, conserva Revisar resultado. No se modificaron los estados ni métricas históricas de las dos tareas incompletas.

Se agregaron spans task.target.stabilize y task.target.verify con destino, y appium.apk.install y appium.session.create, para distinguir espera, instalación y creación real de sesión. Se consultó Get Element Rect de la especificación W3C: https://www.w3.org/TR/webdriver2/#get-element-rect . La implementación nativa se comprobó en el piloto real con UiAutomator2.

## Validación y límites

71 pruebas pasan con salida 0, incluyendo espera mientras cambia la posición, ausencia de clic si no hay estabilidad y recuperación de referencia solo para lectura. Piloto local de tres tarjetas completado con tres ya marcadas; no se borraron datos para producir likes nuevos ni se reejecutaron los dos dispositivos con resultados inciertos.

El piloto tardó aproximadamente 18.0 s frente a 16.7 s de otra muestra previa; NO se afirma mejora de velocidad. La estabilidad agrega comprobaciones. La hipótesis de reducción de fallos requiere nuevos lotes y más muestras. En el piloto la estabilización tardó entre 0.64 y 1.14 s y la verificación alrededor de 80 ms.

La instrumentación separó apertura: instalación APK 0.43 s, creación de sesión 4.73 s. Por ello omitir reinstalaciones no resolvería la mayor parte del costo y podría reintroducir el problema documentado de APK antigua con noReset. No se eliminó esa protección.

## Próximas mejoras justificadas, todavía no aplicadas

1. Probar snapshots en dos placas a la vez, manteniendo una operación por identidad y midiendo carga/tiempo. Es una oportunidad para reducir la espera inicial de unos 60 s; no se prometió dividirla exactamente por dos.
2. Clasificar listeners mediante comprobación del protocolo antes de tratarlos como servidores; conservar compatibilidad con puertos personalizados y no ocultar errores de puertos configurados.
3. Medir estabilidad en lotes nuevos y comparar fallos por tarjeta y dispositivo; mantener las verificaciones de resultado y no recurrir a clics ciegos o reintentos de acciones inciertas.
4. Medir cuándo valdría mantener sesiones por dispositivo para trabajos sucesivos, considerando recursos y desconexiones; no asumir que una sesión puede compartirse entre placas.

## Reproducir el análisis

```powershell
# Cruza trazas recientes y último lote de varias placas, sin modificar estados
.\.venv\Scripts\python.exe -m scripts.review_results --output data/log-review-latest.json
# Seleccionar un lote histórico explícito
.\.venv\Scripts\python.exe -m scripts.review_results --batch-id UUID_LOTE
```

Se conserva el informe agregado local en data/log-review-latest.json. El script informa cuántos eventos entraron y si alcanzó el límite de 10000; las medianas son sobre esa ventana, no sobre toda la historia.
