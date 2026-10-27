# TikTok: detección de apertura y configuración inicial · v2.19

Fecha: 2026-10-26, America/Guatemala.

## Evidencia nueva

El usuario observa que abrir manualmente funciona y aporta captura: pantalla Panda 56 muestra TikTok en configuración inicial «Cuéntanos más cosas sobre ti», con aviso Android de pantalla completa. Esto demuestra apertura en ese instante, no cuenta configurada ni readiness para likes. La ausencia de perfil/cuenta reportada por el usuario no se ha auditado por dispositivo y no se considera un requisito para lanzar el paquete.

Consulta real, solo de lectura:

- Pantalla 24: dumpsys activity activities declara ResumedActivity con el paquete com.zhiliaoapp.musically; no tiene la variante mResumedActivity que aceptaba nuestro lector.
- Pantalla 56: declara mResumedActivity y ResumedActivity de TikTok. Su resultado original del lote indica cancelación durante preparación, no fallo demostrado de lanzamiento.

## Causa confirmada y corrección

El lector de primer plano omitía ResumedActivity sin prefijo m. Esto producía un falso «sin confirmar» en la 24 aunque TikTok estuviera abierto. La misma función se usa para esperar después de lanzar y para la comprobación posterior; ambas reciben la corrección.

Se reconocen mResumedActivity:, ResumedActivity:, topResumedActivity= y mCurrentFocus= al inicio de la línea correspondiente. No se aceptan registros históricos/lastResumedActivity. Si varias actividades actuales declaran paquetes distintos, se conserva estado desconocido para revisión en vez de elegir una arbitrariamente.

No se agregaron pulsaciones de bienvenida, género, aceptación de condiciones, permisos ni login. Abrir la app y tener cuenta/configuración listas siguen siendo conceptos separados. La configuración inicial visible requiere resolver el flujo con el usuario antes de mapear likes.

## Verificación posterior real

105 pruebas correctas, incluidas variantes de etiquetas, historial ignorado y múltiples paquetes ambiguos. Nueva comprobación por scripts.verificar_apps a las 19:51 GT: 15 apps en primer plano y 14 tareas canceladas omitidas, sin casos de primer plano desconocido en las 15 consultadas. No se relanzaron apps durante esta comprobación.

El lote original conserva 13 aperturas completadas, dos resultados para revisar y 14 cancelaciones. La lectura actual de 15 abiertas no se reescribe como éxito automático histórico: la 56 pudo abrirse manualmente. El indicador compacto usa la verificación más reciente; el resultado original sigue en su columna.

Los dumps detallados de diagnóstico solo quedaron en data/tiktok-diagnostic-24.json y data/tiktok-diagnostic-56.json, excluidos de Git. No se versionan datos de cuentas ni capturas privadas. No cambió el esquema SQLite.
