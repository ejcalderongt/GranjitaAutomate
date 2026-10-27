# Verificación posterior de apps · v2.17

Fecha: 2026-10-26, America/Guatemala.

## Flujo

1. El trabajador de apertura procesa las placas elegidas y registra sus resultados originales.
2. Al terminar, otro trabajador muestra Verificando ejecución… y relee identidad Android y actividad en primer plano.
3. El indicador muestra LOTE TERMINADO y VERIFICACIÓN POSTERIOR TERMINADA, junto al resultado de cada fase.

En el panel se utiliza otro QThread, no otro ejecutable. El programa permanece abierto y responde mientras se comprueba. También hay una CLI que puede ejecutarse en otro proceso Python:

```powershell
.\.venv\Scripts\python.exe -m scripts.verificar_apps
```

El botón Verificar último lote permite una lectura nueva, sin repetir la apertura. Se habilita para el último lote terminado de app_prepare. No se aplica a los flujos de likes del laboratorio: su sesión Appium termina la app por diseño y evaluar primer plano después produciría un diagnóstico engañoso.

## Qué comprueba

Valida serial físico y origen ADB; consulta dumpsys activity activities y compara la actividad enfocada con los paquetes admitidos por el perfil. No relanza, instala, hace scroll, acepta diálogos ni pulsa likes. No verifica login, Internet, publicación ni estado del botón de like.

- Abierta en primer plano: coincidencia positiva observada.
- No está en primer plano: se observó otra app; puede estar en segundo plano o cerrada.
- No se pudo comprobar: actividad no identificable o error/identidad no validada.
- Sin ejecutar: tarea cancelada, expirada, interrumpida o no ejecutada; no se consulta esa placa para atribuir una apertura a este lote.
- Verificación cancelada: se interrumpió esta segunda fase; no se reinterpreta el resultado original.

La columna Verificación posterior conserva fecha/hora. Abierta ahora significa el instante de esa lectura, no vigilancia continua. El cierre del lote no garantiza éxito de todas las placas: mantiene Requiere revisión o Con cancelaciones cuando corresponde. Si falta alguna comprobación, el resumen la presenta pendiente.

## SQLite y auditoría

Nueva tabla aditiva app_verifications (id, task_id, at, payload), con historial de cada comprobación, conservando tasks y su detalle original. Antes de añadirla a una base existente se crea automation-antes-verificacion-app.sqlite3. Los lectores toleran una base anterior sin esa tabla; no necesitan construir JobStore ni recuperar estados para consultar.

No se modifica el número de likes ni se reescriben resultados antiguos. Traces relaciona app.source.verify con task_id; feedback y tareas se conservan al limpiar logs. Cancelar esta fase se aplica entre consultas; la lectura ya enviada puede terminar antes de parar.

## Validación real

Comprobación por CLI en proceso separado sobre lote 48dfacb8-0648-4599-a01a-277fa5f1f795, posterior a la limpieza de logs y sin abrir apps:

- Resultado original: 13 aperturas, dos sin confirmar y 14 canceladas, de 29 dispositivos.
- Segunda lectura: 13 en primer plano, una con otra app en primer plano, una actividad no identificable y 14 sin ejecutar (omitidas).
- 29 resultados de comprobación guardados; no se hicieron 29 aperturas ni se consultaron las 14 canceladas.

101 pruebas correctas: lectura sin lanzamiento, distintos estados de primer plano, omisión de canceladas, fallos de consulta, historial de verificaciones sin modificar tareas/métricas y transición GUI entre ambos trabajadores. Revisión visual del resumen y columna nuevos.

El lote de apertura sigue requiriendo revisión y los likes de TikTok siguen pendientes de mapeo. Esta verificación aporta evidencia nueva; no simula resolver esos pendientes.
