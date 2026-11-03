# Auditoría del smoke test — 2026-10-29

## Resultado

**No existe una ejecución smoke iniciada en esta instalación.** No corresponde
clasificarla como aprobada ni como fallo de las placas. Lo aprobado es la prueba
de conectividad de los tres proxies de laboratorio.

## Evidencia contrastada

| Fuente | Hallazgo |
| --- | --- |
| SQLite, `ejecuciones_granja` | 0 ejecuciones; no hay run_id de smoke |
| SQLite, `interacciones` | 0 interacciones y 0 ciclos IA |
| SQLite, `proxy_reservas` | 0 reservas |
| `sessions/farm/` | Sin directorios de ejecución |
| `sessions/farm_ui/` | Sin procesos lanzados ni process.log |
| `sessions/local_proxy/verification.json` | HTTPS Windows y Android aprobado en 8001, 8002 y 8003; apps_launched=false |
| Dashboard observado | Proxies habilitados: 3; API OpenAI: pendiente de configurar |
| Dashboard observado | 33 conectadas, 34 identidades físicas conocidas y 0 ciclos IA |

Se comprobó únicamente la presencia de OPENAI_API_KEY, sin leer ni revelar
valores: ausente en el proceso de auditoría y en las variables de usuario y
máquina de Windows. El propio dashboard confirma que su API está pendiente.

Los registros de bootstrap disponibles son históricos del 2026-10-28; no son
un nuevo smoke ni acreditan encendido en frío. El log de 179 pruebas corresponde
a tests de software, no a 179 ciclos en teléfonos reales.

## Bloqueo y límite del diagnóstico

`FarmJobs.start` valida el pool, el binario y OPENAI_API_KEY antes de crear el
directorio de ejecución o invocar Popen. La ausencia de la clave es un requisito
pendiente confirmado, compatible con que no haya proceso ni logs del smoke.
No hay una traza persistida del clic del operador que permita afirmar cuál fue
el mensaje exacto de un intento anterior.

La interfaz atrapa el error y lo muestra mediante st.error; esa rama no lo guarda
en SQLite ni en un archivo de intentos. Esta es una carencia de observabilidad:
los rechazos previos al arranque deben registrarse con fecha, fase, modo y motivo,
sin guardar credenciales.

Tampoco se ejecutó el Auth Check de las placas. Cero dispositivos en Pendiente
Cuenta no demuestra que tengan una sesión válida: el dashboard muestra 34
cuentas sin comprobar.

## Próximos pasos

1. Configurar OPENAI_API_KEY de forma local en el servidor.
2. Reiniciar el dashboard para que herede la variable y cargue los módulos actuales.
3. Lanzar el smoke de tres placas y un ciclo desde el panel.
4. Auditar el nuevo run_id: logs por worker, comprobación de identidad/cuenta,
   IP verificada, decisión IA, duración, limpieza y resumen de salida.

Esta auditoría fue de lectura y documentación: no se pulsó Iniciar, no se
consultó OpenAI y no se abrió TikTok. El resumen estructurado está en
`sessions/audits/smoke-2026-10-29.json`.

## Actualización posterior: credencial configurada

El mismo 2026-10-29, por instrucción del operador, se importó su clave a `.env`
privado y se integró su carga como OPENAI_API_KEY al iniciar el proyecto. Se
reinició únicamente el dashboard, que confirmó **API OpenAI: configurada**.
Esta actualización resuelve el requisito local de configuración; no constituye
una autenticación remota comprobada ni una ejecución smoke. No se registró el
valor de la credencial en esta documentación ni en los logs.
