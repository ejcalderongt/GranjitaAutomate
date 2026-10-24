# Laboratorio de automatización v1

Fecha de inicio: 2026-10-24. Desarrollo en curso.

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

test_lab selecciona una sola conexión validada con serial sin conflicto, revalida su identidad, instala/abre la APK de prueba mediante Appium y verifica like, comentario y scroll. No controla aplicaciones sociales. La primera prueba completa pasó en una placa del servidor 5037. Continúa la comprobación de un lote con ambos servidores; se detectó una diferencia de comportamiento de foco/scroll que requiere estabilización antes de dar por validado el lote.

## Persistencia

Las tareas se guardan en data/automation.sqlite3 y la evidencia en data/lab-evidence. Se conserva estado, placa, servidor, comentario local, resultado y fechas. No se reintentan automáticamente tareas cuyo resultado quedó incierto después de una interrupción.

## Automate

El adaptador base diagnostica instalación y accesibilidad y puede abrir Automate en una placa seleccionada. La instalación oficial se realiza desde Google Play. El usuario autorizó intentar la instalación remota en una placa de pruebas. No se automatizan inicios de sesión ni se conceden permisos sensibles silenciosamente. La ejecución de flujos Automate aún requiere instalación, configuración y verificación; no se da por completada por abrir la aplicación.

## Fuentes

- https://appium.github.io/appium-uiautomator2-driver/latest/reference/capabilities/
- https://llamalab.com/automate/
