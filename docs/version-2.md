# GranjitaAutomate v2.0 — inventario y servidores ADB

## Uso

Abrir el mismo acceso directo **GranjitaAutomate** del escritorio. La búsqueda inicial consulta los puertos 5037 y 5038, más los puertos que Windows identifique como escuchas de procesos adb. La detección de procesos puede estar restringida por permisos; aun así se consultan los puertos configurados.

El panel superior muestra servidor y puerto, PID cuando está disponible, respuesta ADB, cantidad de conexiones y hora de comprobación. Un puerto sin respuesta no se considera un servidor ADB activo. Los datos persistidos se muestran pendientes de verificar hasta completar la búsqueda.

La tabla inferior combina las conexiones y conserva el puerto de origen. **Conexiones** y **fichas** son conceptos diferentes: una placa puede tener varios transportes. No se fusionan automáticamente por IP, modelo ni número de serie declarado.

- **Buscar y validar / Reintentar:** actualiza servidores y conectividad.
- **Inventariar seleccionada:** captura datos de la conexión elegida, previamente validada.
- **Inventariar todas:** consulta todas las conexiones validadas con hasta cuatro operaciones concurrentes. No se mezcla con otra búsqueda o inventario.
- **Ver ficha** o doble clic: muestra sistema/root, red/USB, recursos/ajustes y aplicaciones.
- **Cambiar nombre:** asigna un alias a la ficha.
- **Asociar conexión a otra ficha:** permite al usuario confirmar que dos conexiones pertenecen a la misma placa física. Verificar las series en ambas fichas antes de confirmar. Conserva el historial al transferir una ficha que ya no tiene otros transportes.
- **Configuración:** cambia la lista de puertos locales, separados por coma.
- **Respaldar SQLite:** crea una copia consistente con todos los datos.

La revisión opcional cada 30 segundos comprueba conexiones. El inventario detallado se actualiza con sus botones, para evitar recopilar paquetes y ajustes continuamente.

## Datos disponibles

34 observaciones por captura: fabricante/modelo, series declaradas, Android/API, compilación/parche, arquitecturas, idioma/zona horaria, USB, direcciones por interfaz, rutas IPv4/IPv6, redes activas/DNS disponibles, DNS privado, proxy global, Wi-Fi actual, ajustes de Wi-Fi/datos móviles, batería, almacenamiento, identidad ADB, presencia de su, evaluación de root, depuración, accesibilidad y paquetes con código de versión.

Cada observación conserva valor, resultado, comando de origen y fecha. Valores ausentes se distinguen de errores y restricciones. Los cambios de valor o resultado se resaltan frente a la captura anterior. La fecha de la captura se muestra aunque la conexión siga activa: conexión actual no implica inventario actualizado.

Root solo se confirma cuando la sesión consultada devuelve UID 0. Encontrar su es un indicio; no encontrarlo no prueba ausencia. No se ejecuta su, no se conceden permisos, no se cambia la configuración Android ni se extraen contraseñas de redes. No se consulta la IP pública ni se envía el inventario a servicios externos. La salida de conectividad se limita a líneas de redes y enlaces; la disponibilidad depende de Android y permisos.

## Persistencia y migración

SQLite sigue en `data/granjita.sqlite3`, excluida de Git. Antes de migrar v1 se crea `data/granjita-antes-v2.sqlite3`. Se conservan alias y eventos previos; las conexiones anteriores quedan pendientes de validar. El esquema v2 agrega identidades internas UUID, conexiones por puerto/identificador, servidores, instantáneas, observaciones y eventos.

Una caída de servidor marca sus conexiones **Servidor sin verificar**; solo una búsqueda exitosa donde falta una conexión la marca **Desconectado**. No hay reinicios de ADB ni escaneos de red a las placas.

Se evita abrir simultáneamente más de una instancia de v2 en la misma carpeta. Cerrar la versión anterior antes de actualizar. Las capturas guardadas y sus paquetes son datos locales privados; respaldarlos mediante el botón, no subirlos a Git.

## Comprobaciones del 2026-10-23

- Servidores 5037 y 5038: 17 y 16 conexiones respectivamente, 33 validadas en conjunto.
- Inventario completado para las 33 conexiones: 34 observaciones por captura.
- Evaluación de root: 14 con indicios de su y 19 sin indicios observados; ninguna ejecución de su.
- Once pruebas automatizadas de protocolo, inventario, respaldo, migración, agregación, fallo parcial, persistencia, cambios, asociación explícita y ocultación de credenciales de proxy.
- Revisión visual de tabla de servidores, inventario y ficha.

## Herramienta reproducible

```powershell
.\.venv\Scripts\python.exe -m scripts.inventariar
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

La primera orden actualiza la base local con inventario de las conexiones validadas. Su salida imprime agregados, sin identificadores privados.

## Pendientes

Reconciliar registros desconectados de Panda, validar el proceso físico OTG y evaluar tareas/Automate en una fase posterior. El inventario de aplicaciones informa paquetes y códigos de versión; no lee sesiones ni datos internos de cuentas. No se instaló una app Android ni se integró IA en esta fase.
