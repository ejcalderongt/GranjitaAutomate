# Arranque, conciliación y diagnóstico del rack

Fecha: 2026-10-24, America/Guatemala. Versión 2.4.

Al iniciar y al pulsar Conciliar y conectar, la aplicación comprueba el proceso de Panda, lo abre si falta y conoce su ruta, consulta su API y descubre los servidores ADB. Reintenta conexiones TCP privadas previamente inventariadas solamente en un servidor de origen que responda. Limita la pasada a 64 destinos y cuatro consultas simultáneas, con tiempos límite. No explora subredes, no reinicia ADB ni activa tcpip/USB por shell. El origen histórico puede cambiar tras un reinicio: si no responde, requiere revisión en Panda, sin redistribuir conexiones a ciegas.

Omite transportes ya presentes y seriales físicos que ya respondan. Entre varias conexiones históricas de una misma placa elige una sola. Tras los intentos valida nuevamente por ADB/getprop; una respuesta de connect no basta para declarar activa. La conciliación conserva las protecciones contra IP reutilizada e identidad en conflicto. Las filas activas se muestran primero y en verde; hay columnas Panda y Diagnóstico / siguiente paso. El resumen separa seriales físicos y transportes. Una ficha histórica puede tener varias conexiones; las filas no equivalen a placas distintas.

La consulta de Panda se repite después de la búsqueda si inicialmente estaba vacía. La pertenencia a su lista y mode=2 indican reconocimiento/método OTG según Panda, no constituyen una medida eléctrica ni bastan para el verde. Un fallo de API se muestra como sin comprobar. Informe local: data/reconciliation-latest.json, excluido de Git.

## Límites de arranque en frío

No se ha realizado un apagado del equipo/rack en esta sesión. No está demostrado todavía que todas las placas arranquen automáticamente tras recuperar energía. El flujo esperado es encender PC y fuente/rack, pulsar el botón físico de encendido si ese modelo lo exige, abrir GranjitaAutomate y esperar la conciliación. Si Android pierde su configuración o autorización de depuración, o Panda requiere completar OTG, habrá intervención guiada. La API Android documentada consultada no enumera una operación específica para habilitar OTG desde cero. No se prometió automatizar un botón físico sin controlador compatible.

## Energía y socket

Inspección Windows: dos concentradores USB genéricos y un concentrador raíz reportaron OK. No se identificó un controlador de rack con telemetría por socket. Esto no prueba que no exista; falta marca/modelo/manual y correspondencia de ranuras. Un hub enumerado no demuestra tensión/corriente correcta en cada placa; ADB ausente tampoco demuestra falta de energía. dumpsys battery en una placa accesible es evidencia del sistema Android, no una medición independiente de la fuente del rack.

Para una placa que no responde: comprobar indicadores de fuente/rack y tiempo de arranque; comparar con otra placa funcional; revisar cable y conexión OTG/red; probar cable/puerto conocidos siguiendo el manual y con el equipo desenergizado cuando el fabricante lo requiera. Si el fallo sigue a la placa, revisar placa/arranque; si permanece en la ranura, revisar cable/socket/controlador. Confirmar eléctricamente requiere telemetría de corriente/tensión por canal o medición física adecuada. No hay actualmente encendido/corte remoto ni lectura eléctrica implementados.

Próximo inventario físico: rack, ranura, serial, cable, hub/puerto y canal de energía, más interfaz del controlador si existe. No asociar una IP cambiante a un socket sin evidencia.

## Validación y hallazgo

37 pruebas automatizadas pasan con salida 0. Se ejecutó conciliación real y se comprobó renderizado de once columnas y orden de activos. La primera prueba reintentó transportes históricos en varios orígenes y expuso duplicados de conexión; se corrigió para deduplicar candidatos por serial físico y omitir placas ya accesibles. No se desconectaron transportes existentes para limpiar esa observación ni se contó cada transporte como placa. Quedan pendientes la prueba física tras corte completo y verificar el controlador del rack.

Referencias oficiales: https://doc.some3c.com/panda-manual/api-documentation y https://developer.android.com/tools/adb (conexión/arquitectura ADB).

## Identificación visual aportada por el usuario · 2026-10-24

El usuario indicó que no encuentra marca ni modelo físicamente. Aportó dos capturas de un anuncio/pedido de Amazon: el título visible es «Android Phone Farm Server Box System Farming Machines Hub U…» y la variante indica «20-phone farm». La imagen muestra un chasis de placas verticales y ventilación superior. No se distingue una referencia de controlador, fuente, puertos ni etiquetas eléctricas. La imagen comercial no demuestra que el interior de las unidades instaladas coincida exactamente.

Una búsqueda por el título encontró publicaciones de aspecto/nombre semejantes con varias variantes y vendedores; no permitió identificar inequívocamente la unidad ni hallar su manual de controlador. No se asigna al rack una marca, potencia, tensión o API a partir de coincidencias comerciales. Las capturas del pedido se mantienen fuera del repositorio.

Siguiente evidencia útil: enlace del artículo original o ASIN de Amazon (habitualmente B0…), y fotografías externas de conexiones, interruptores e indicadores de una unidad. El enlace/ASIN ayuda a identificar al proveedor; no requiere datos del pedido, dirección ni pago. Si no hay controlador documentado, se mantiene diagnóstico por software y prueba física guiada; energía y corriente por ranura siguen desconocidas.

## Prueba física reportada · 2026-10-24, 17:00–17:02 GT

Fuente: mensajes de prueba compartidos por el usuario y fotografía del rack. Evidencia reportada por operador; no se ejecutó una comprobación remota adicional en este registro.

| Posición física reportada | Pantalla Panda reportada | Resultado reportado |
| --- | --- | --- |
| 10 | 65 | Retirada/reinsertada; recuperación final pendiente de aclarar. |
| 17 | 30 | Retirada/reinsertada; no recuperada según el relato. |
| 20 | 51 | Regresó a pantalla y tiene Internet según prueba de navegación; indicador descrito como azul. |

Se reportó que retirar físicamente las tarjetas hacía desaparecer/apagar sus vistas en el monitor y que fue necesario Habilitar y Escanear en Panda para recuperarlas. La primera impresión de recuperación de todas fue corregida por el operador. Existe contradicción textual: escribió que solo volvió 51, pero también «30 y 51 no regresó»; la mención final confirma Internet en 51=20. No sustituir silenciosamente el segundo 51 por 65: pedir aclaración.

La fotografía muestra posiciones numeradas 1–20, iluminación de distintos colores y un puerto frontal rotulado OTG/USB junto a conexión de red. No proporciona una leyenda de los LED, marca/modelo ni medida eléctrica. Las posiciones son locales al chasis: falta identificar a cuál rack pertenecen. No asociarlas automáticamente a seriales de inventario ni usar el número Panda como identidad permanente.

Conclusión limitada: un indicador descrito como azul es compatible con funcionamiento e Internet en la placa 20 según la prueba. No se debe usar azul=avería ni verde=Android/Internet comprobados. Una luz es evidencia de actividad eléctrica en algún circuito, no confirma que toda la placa reciba tensión/corriente correcta. La recuperación mediante Habilitar/Escanear indica que el procedimiento de Panda intervino; no identifica por sí solo cuál paso resolvió el transporte ni equivale a una prueba de arranque en frío del conjunto.

Próxima prueba: confirmar las dos pantallas ausentes; consultar su estado en Panda y los servidores ADB; mapear rack/posición a serial verificado cuando respondan. Si una placa sigue ausente, comparar placa y ranura conocidas siguiendo el manual y sin asumir que admite extracción en caliente. Si el problema sigue a la placa, investigar placa/adaptador; si permanece en la posición, investigar socket/cable/alimentación. Es un método de aislamiento, no un diagnóstico eléctrico definitivo.


### Aclaración confirmada por el usuario · 2026-10-24

El usuario confirmó que las pantallas que no regresaron fueron 30 (tarjeta física 17) y 65 (tarjeta física 10). Pantalla 51 (tarjeta física 20) sí recuperó imagen e Internet según la prueba reportada. Esto resuelve la contradicción del mensaje original; no constituye una nueva comprobación remota ni confirma falla eléctrica de las otras dos placas. Sigue pendiente identificar el rack y vincular las posiciones a seriales verificados.
