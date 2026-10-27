# GranjitaAutomate

Repositorio de conocimiento, documentación y herramientas para administrar la granja de placas Android.

## Aplicación v2.18

Abrir **GranjitaAutomate** desde el escritorio o ejecutar `iniciar.vbs`. Consulta la [guía de inventario y servidores ADB](docs/version-2.md) y las [instrucciones de instalación](docs/version-1.md). Usa SQLite local en `data/`, excluida de Git.

La [identificación por serial físico](docs/identidad-dispositivos.md) propone nombres automáticos, conserva alias y detecta conflictos de identidad.

El botón **Automatización** abre las pruebas locales por lote y la preparación de apps origen. El [perfil de aplicación origen](docs/app-origen.md) permite seleccionar Granjita Lab o TikTok y abrir/comprobar la app; los likes de TikTok aún requieren mapeo y validación. Consulta la [guía del laboratorio](docs/laboratorio-appium.md) para instalación, alcance, resultados y permisos pendientes de Automate.

La opción **Avanzado → Conexión y diagnóstico → API Panda** compara el inventario de Panda y el local. La [guía de API y recetas](docs/api-panda-y-recetas.md) explica los perfiles JSON, las recetas ejecutables y la propagación verificable de herramientas.

El arranque intenta conciliar y reconectar transportes conocidos; muestra comparación con Panda y diagnóstico. Consulta [arranque y límites del rack](docs/arranque-y-rack.md).

El [orden físico permanente](docs/orden-fisico.md) conserva rack y posición por serial, con activos primero opcional y asignación verificada desde la aplicación.

Los [snapshots 4.2](docs/subfase-4-2-snapshots.md) guardan inventario y archivos propios en SQLite; al iniciar verifican y recuperan archivos ausentes sin sobrescribir los existentes. Consulta el [registro ordenado de versiones](docs/versiones.md).

El [primer flujo de Me gusta](docs/flujo-likes.md) se ejecuta en Granjita Lab, sin comentarios ni scroll, y conserva resultados en SQLite.

Las [métricas de likes](docs/metricas-likes.md) distinguen aplicados, ya marcados y sin confirmar, con auditoría exportable por tarea y destino.

El [creador de tareas](docs/creador-tareas.md) muestra dispositivos en línea/aptos/seleccionados y permite configurar cantidad de likes, scroll y ventana de inicio/fin de Guatemala.

La [pantalla principal guiada](docs/ui-principal.md) organiza el uso en tres pasos y reúne las funciones técnicas en Avanzado.

Los [logs y trazas](docs/logs-y-feedback.md) registran tiempos y resultados por proceso/tarea en SQLite. El visor de Avanzado permite exportar ejecuciones y registrar feedback.

La [revisión de logs](docs/revision-logs-2026-10-24.md) cruza resultados del lote, fallos y tiempos; el flujo ahora espera estabilidad del botón y verifica sin repetir clics inciertos.

El [indicador de likes logrados](docs/indicador-likes.md) muestra nuevos verificados e historial por dispositivo y tarjeta, con filtros y evidencia disponible.

El [diagnóstico del último lote](docs/revision-batch-2026-10-26.md) distingue apertura de app, mapeo pendiente y ejecución de likes; el panel muestra app/acción y resumen del último lote.

La [limpieza de logs y cierre de lotes](docs/limpieza-logs-y-resumen.md) permite archivar trazas para una prueba nueva y ver si terminó el lote, cuántas apps se abrieron y cuántas quedaron sin confirmar.

La [verificación posterior](docs/verificacion-posterior-apps.md) relee el primer plano al terminar la apertura, en un trabajador separado, y conserva el resultado de ejecución junto a la comprobación independiente.

El [resumen compacto del lote](docs/resumen-compacto-automatizacion.md) muestra estado, tres indicadores y verificación; el detalle sigue disponible en la tabla y al pasar el cursor.

## Organización

- [Contexto de la granja](docs/contexto.md): información recuperada y datos por confirmar.
- [Pendientes](docs/pendientes.md): próximos pasos.
- [Bitácora](docs/bitacora.md): registro de avances y decisiones.
- `scripts/`: herramientas y automatizaciones que vayamos desarrollando.

## Forma de trabajo

Guardar aquí el conocimiento útil y los archivos creados. Cada avance debe incluir documentación suficiente para retomarlo y un commit descriptivo. Sincronizar con GitHub al terminar cada bloque de trabajo, cuando haya conexión y autorización de acceso.

No guardar contraseñas, tokens, códigos de activación, cookies ni datos privados de cuentas. Las capturas deben revisarse antes de incluirlas.

Fecha de inicio: 2026-10-23 (America/Guatemala).
