# Pendientes

- [ ] Confirmar inventario y conexiones actuales de las placas.
- [ ] Confirmar activación de Panda VIP.
- [ ] Incorporar documentación y herramientas previas que el usuario identifique.
- [x] Definir y documentar el primer trabajo técnico: asistente de conexión v1 con SQLite.
- [x] Validar arquitectura y conexión principal: OTG mediante el proceso de Panda.
- [x] Localizar ADB de Panda y comprobar acceso no disruptivo al servidor local existente.
- [ ] Probar con el usuario el flujo físico OTG y la recuperación guiada de una placa desconectada o sin autorización.
- [ ] Integrar visualización opcional con scrcpy si se necesita además de Panda.
- [x] Corregir detección para combinar servidores ADB 5037 y 5038, conservar origen y evitar falsos desconectados entre servidores.
- [ ] Reconciliar los 41 registros de Panda con los 33 dispositivos accesibles detectados en ambos servidores.
- [x] Fase 2: implementar inventario detallado con evidencias, identidad interna independiente de IP e historial de cambios; ver docs/version-2.md. La asociación física entre transportes es manual y explícita.
- [x] Mostrar estado de servidores ADB, puertos, PID disponible y conexiones por servidor.
- [ ] Evaluar piloto de tareas mediante ADB/Automate frente a agente Android propio en una aplicación de prueba.
- [ ] Fase 3: definir proveedor de IA, manejo de credenciales, contexto permitido y ejecución supervisada.
