# Framework QA: respaldo del 2 de noviembre de 2026

El desarrollo de la carpeta local `Framwork` se incorpora bajo `framework/`.
La aplicación histórica `granjita/` se conserva. Esta entrega es una copia de
código y documentación, no una migración ni sustitución de bases de datos.

## Verificación confirmada

- 319 pruebas aprobadas el 2026-11-02 en la suite del framework.
- Panel Tkinter por tarjetas, alertas estructuradas de red y progreso por ciclos
  correctos; revisado visualmente con datos de ejemplo sin tráfico externo.
- Ruta web async de solo lectura: scraper acotado al video activo, agente de
  análisis textual y telemetría SQLite sin contenido de feed en las tablas QA.
- Consentimiento de cookies acotado a cinco segundos; no garantiza que todos
  los diálogos actuales de TikTok se reconozcan.
- Último smoke real: SOCKS5 y HTTPS verificados; fallo antes del feed con
  filtro EU activo, cero ciclos de IA. No se acreditaron likes o comentarios.
- El helper Android no tiene un motor TCP embebido operativo. No afirmar
  aislamiento hermético ni VPN operativa por la existencia del APK.

## Reproducir

Trabajar desde `framework/`, no desde la raíz del repositorio histórico.
Crear allí un entorno Python 3.11+ y seguir `framework/docs/INSTALACION_WEB.md`
y `framework/docs/POC_UI.md`. El launcher es:

```powershell
cd framework
.\.venv\Scripts\python.exe -m ui.poc_dashboard
```

Para recrear el acceso del Escritorio, ejecutar
`framework/scripts/crear_acceso_directo.ps1` una vez instalado el entorno.
La suite hermética se ejecuta con `python scripts/run_tests.py` desde framework.
Configurar las credenciales localmente conforme a las plantillas y documentación.

## Exclusiones y continuidad

No se incluyen `.env`, credenciales de proxy, cookies, sesiones, SQLite,
evidencias, logs, dependencias descargadas ni APK/binarios de `tools/`.
La BD histórica y la telemetría requieren respaldo privado separado.
El archivo local `config/web_accounts.json` tampoco se versiona: usar su ejemplo.

La carpeta original `Framwork` permanece intacta y su Git independiente no está
conectado a esta subcarpeta. Para futuros commits trabajar en este checkout
`framework/` o copiar/revisar explícitamente los cambios; no asumir sincronización
automática entre carpetas. No se alteraron los cambios pendientes del checkout AGX.
