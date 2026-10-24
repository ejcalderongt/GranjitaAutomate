# GranjitaAutomate

Repositorio de conocimiento, documentación y herramientas para administrar la granja de placas Android.

## Aplicación v2.4

Abrir **GranjitaAutomate** desde el escritorio o ejecutar `iniciar.vbs`. Consulta la [guía de inventario y servidores ADB](docs/version-2.md) y las [instrucciones de instalación](docs/version-1.md). Usa SQLite local en `data/`, excluida de Git.

La [identificación por serial físico](docs/identidad-dispositivos.md) propone nombres automáticos, conserva alias y detecta conflictos de identidad.

El botón **Laboratorio Appium / Automate** abre las pruebas locales por lote. Consulta la [guía del laboratorio](docs/laboratorio-appium.md) para instalación, alcance, resultados y permisos pendientes de Automate.

El botón **API Panda** compara el inventario de Panda y el local. La [guía de API y recetas](docs/api-panda-y-recetas.md) explica los perfiles JSON, las recetas ejecutables y la propagación verificable de herramientas.

El arranque intenta conciliar y reconectar transportes conocidos; muestra activos primero, comparación con Panda y diagnóstico. Consulta [arranque y límites del rack](docs/arranque-y-rack.md).

## Organización

- [Contexto de la granja](docs/contexto.md): información recuperada y datos por confirmar.
- [Pendientes](docs/pendientes.md): próximos pasos.
- [Bitácora](docs/bitacora.md): registro de avances y decisiones.
- `scripts/`: herramientas y automatizaciones que vayamos desarrollando.

## Forma de trabajo

Guardar aquí el conocimiento útil y los archivos creados. Cada avance debe incluir documentación suficiente para retomarlo y un commit descriptivo. Sincronizar con GitHub al terminar cada bloque de trabajo, cuando haya conexión y autorización de acceso.

No guardar contraseñas, tokens, códigos de activación, cookies ni datos privados de cuentas. Las capturas deben revisarse antes de incluirlas.

Fecha de inicio: 2026-10-23 (America/Guatemala).
