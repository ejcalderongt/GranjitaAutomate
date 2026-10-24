# Fases 2 y 3

Fecha: 2026-10-23. Requisitos expresados por el usuario; diseño propuesto, todavía sin implementar.

## Fase 2: inventario verificable

Primero incorporar los servidores ADB 5037 y 5038. Conservar conexiones por separado de la identidad física de la placa; una IP no es una identidad estable. No fusionar placas basándose solamente en modelo o IP.

Ficha por dispositivo:

- Identidad: identificador interno, alias, fabricante, modelo y número de serie cuando sea accesible.
- Sistema: versión Android, API, compilación, parche de seguridad, arquitectura, idioma y zona horaria.
- Conexiones: servidor ADB de origen, identificador de transporte, IP por interfaz, red activa, rutas, DNS y proxy configurado cuando sean consultables. Diferenciar dirección ADB, IP local e IP pública; esta última exige una consulta externa explícita.
- Recursos: batería, carga y almacenamiento disponible.
- Software: paquetes instalados, versiones y capacidades necesarias para tareas futuras.
- Privilegios: UID de la sesión ADB, indicios de su y evidencia de root. Estados separados: confirmado, indicios, no observado o no comprobable. No declarar ausencia de root por una prueba negativa. No ejecutar su ni provocar permisos nuevos silenciosamente.
- Configuración relevante: depuración y accesibilidad cuando sean consultables, sin extraer credenciales de redes ni datos privados de cuentas.

Cada observación tendrá valor, fuente, fecha, resultado y error o restricción de permisos. Mostrar desconocido o no disponible cuando corresponda. Guardar instantáneas y cambios, no solamente el último valor.

SQLite propuesto: devices (identidad), connections (transportes), inventory_snapshots y observations (evidencia), packages (software), tasks y task_events (ejecución futura). Migraciones versionadas y respaldo antes de modificar el esquema.

Criterios de aceptación: cobertura de ambos servidores, sin falsos desconectados si falla uno; ficha por placa, evidencia y vigencia visibles; persistencia después de reiniciar; comparación de cambios; errores y permisos diferenciados de valores negativos.

## Ejecución de tareas: opciones

Recomendación inicial: inventario mediante ADB desde Windows y primer flujo reproducible en una aplicación de prueba. Evaluar Automate de LlamaLab con un piloto pequeño para flujos locales. Crear un agente Kotlin propio si se requiere operación autónoma, comunicación persistente o capacidades que el piloto no cubra.

Automate ofrece flujos visuales y acceso ADB; root es una capacidad distinta y no se obtiene por instalar Automate. Una app propia también está sujeta a permisos y restricciones de Android, incluyendo visibilidad de paquetes y datos de red.

Protocolo futuro de tareas: identificador único, placa objetivo, acción permitida, parámetros, precondiciones, plazo, estado, evidencia y resultado. Reintentos limitados; no repetir acciones externas si el resultado anterior es incierto. Pausa y cancelación visibles.

## Fase 3: interpretación con IA

El usuario plantea interpretación contextual para objetivos como agradecer o felicitar y tareas como desplazarse, dar like o comentar, en cuentas controladas y con fines educativos. Esa descripción no demuestra por sí sola compatibilidad con las reglas de cada plataforma; se evaluará la integración concreta.

La IA propondrá una acción estructurada y un borrador; un ejecutor validará objetivo, dispositivo, acción y precondiciones. Empezar con simulación y revisión del contenido antes de publicar, y acotar la ejecución al entorno de prueba definido. No dar a la IA ejecución de shell arbitraria.

La credencial del proveedor de IA se mantiene en Windows, fuera de Git y de las placas; nunca dentro de APK ni del inventario. Definir proveedor, permisos y contenido que se enviará antes de integrar el servicio. Registrar solamente la evidencia necesaria, sin tokens ni credenciales.

## Referencias

- https://developer.android.com/reference/android/net/ConnectivityManager
- https://developer.android.com/training/package-visibility
- https://llamalab.com/automate/doc/adb.html
- https://llamalab.com/automate/doc/block/shell_command_superuser.html
