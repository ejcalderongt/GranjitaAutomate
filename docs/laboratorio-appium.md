# Laboratorio de automatización v1

Fecha de inicio: 2026-10-24. Laboratorio v1 incluido en GranjitaAutomate v2.2.

## Componentes instalados localmente

- Appium 3.8.0, UiAutomator2 8.7.0 y npm 12.2.1, con Node 24 y JDK 21 disponibles en el equipo.
- SDK aislado en .tools/android-sdk, usando el mismo ejecutable ADB de Panda y sus DLL. Cada sesión indica el puerto ADB de la conexión y suppressKillServer=true.
- Appium escucha solamente en 127.0.0.1:4723. No se habilitan comandos shell arbitrarios ni opciones relaxed-security.
- APK Granjita Lab: fuente en android-lab, compilación reproducible con scripts.build_lab, sin permiso INTERNET. Likes y comentarios son datos locales de la app de prueba.

## Preparación reproducible

```powershell
.\.venv\Scripts\python.exe -m scripts.setup_automation
.\.venv\Scripts\python.exe -m scripts.build_lab
.\.venv\Scripts\python.exe -m scripts.test_lab --first-eligible
```

setup_automation descarga dependencias desde npm y la plataforma Android 35 desde Google, comprueba sus sumas de integridad y usa las herramientas instaladas en C:/AndroidSDK/build-tools. Requiere Panda, JDK y Node disponibles. La configuración y todos los binarios quedan fuera de Git.

test_lab selecciona una sola conexión validada con serial sin conflicto, revalida su identidad, instala/abre la APK de prueba mediante Appium y verifica like, comentario y scroll. No controla aplicaciones sociales. La prueba completa pasó en una placa y después en un lote secuencial de tres placas, cubriendo los servidores 5037 y 5038.

La actualización de la APK propia se realiza con adb install -r sobre el servidor y transporte específicos, preservando sus datos. Esto resuelve que noReset del driver omitía actualizar el APK aunque se indicara enforceAppInstall. El ejecutable usado es el mismo de Panda. Se verificó que los PID de ambos servidores ADB permanecieron sin cambios.

## Panel

Abrir el acceso directo habitual y pulsar **Laboratorio Appium / Automate**. Seleccionar una o varias placas sin conflictos de identidad, escribir un comentario local y ejecutar. Un lote de varias placas requiere que antes haya pasado un piloto individual.

Las tareas se ejecutan secuencialmente. Pausar detiene el paso al siguiente dispositivo; cancelar se comprueba entre pasos y evita iniciar las tareas restantes. No se mata una sesión a mitad de una operación del sistema. La interfaz impide cerrar el panel durante la ejecución para no abandonar hilos. Los resultados inciertos se conservan para revisión, sin reintentos automáticos.

La tabla muestra resultados por tarea, detalles y estadísticas de las últimas 300 tareas. Las evidencias son capturas del laboratorio guardadas localmente. Las pruebas de desarrollo fallidas o interrumpidas también quedan en el historial; no son acciones sociales.

Para repetir el lote piloto:

```powershell
.\.venv\Scripts\python.exe -m scripts.test_lab --pilot-batch 3
```

## Persistencia

Las tareas se guardan en data/automation.sqlite3 y la evidencia en data/lab-evidence. Se conserva estado, placa, servidor, comentario local, resultado y fechas. No se reintentan automáticamente tareas cuyo resultado quedó incierto después de una interrupción.

El botón de respaldo del inventario copia granjita.sqlite3; no incluye automation.sqlite3 ni las capturas. Para respaldar todo el laboratorio, cerrar el programa y copiar también automation.sqlite3 y lab-evidence. No versionar esos datos privados.

## Automate

El adaptador base diagnostica instalación y accesibilidad y puede abrir Automate en una placa seleccionada. Se instaló remotamente desde Google Play en UNA placa piloto, se verificó com.llamalab.automate y se aceptó su licencia inicial. No se instaló en las otras placas ni se usaron APK de terceros.

Se creó el flujo **Granjita Lab - abrir laboratorio** en esa placa:

1. Flow beginning, salida GO conectada a entrada IN del siguiente bloque.
2. App start: paquete gt.granjita.lab, actividad gt.granjita.lab.MainActivity, elegidos con Pick activity.

Al pulsar START, Automate exigió aparecer sobre otras aplicaciones, ignorar hibernación e ignorar optimización de batería. No se concedieron esos permisos; se solicitó autorización al usuario y se canceló el diálogo conservando el flujo. Por ello, la ejecución de ese flujo sigue pendiente, aunque la instalación y configuración están hechas. No se necesita accesibilidad para este flujo mínimo, pero otros flujos de interacción de UI sí pueden necesitarla.

Para encontrarlo, seleccionar la placa piloto en el panel y pulsar **Abrir Automate**. Las URI de flujos son locales a cada instalación; no se inventó una URI ni se implementó un disparador remoto sin comprobarlo.

## Validación

20 pruebas automatizadas aprobadas, revisión visual del panel y prueba real secuencial de tres placas. La app de laboratorio permite comprobar acciones locales; esta versión no integra cuentas de redes, modelos de IA ni estadísticas de alcance o impresiones.

## Fuentes

- https://appium.github.io/appium-uiautomator2-driver/latest/reference/capabilities/
- https://llamalab.com/automate/
