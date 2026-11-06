# Contrato de la UI del laboratorio

## Alcance

Esqueleto para E-5 del plan. Panel local sobre el flujo existente.

## Acciones disponibles

Iniciar, pausar, detener y consultar la etapa activa.

## Estado observable

Mostrar etapa, progreso y estado en curso, completado o abortado con una razon legible.

## Evidencia accesible

Por corrida, mostrar los logs, el JSON de resultados y los hashes de invariantes.

## Autorizaciones vigentes

Validar cada accion con el alcance y la autorizacion de la etapa.

## Criterios de aceptacion

E-1. **Interfaz operable.** Existe una UI que permite al operador iniciar, pausar, detener y observar el estado de las etapas del laboratorio.

E-2. **Estado observable.** La UI muestra, en tiempo real o por refresco, el estado de cada etapa: en curso, completada, abortada, con reasons humanos.

E-3. **Evidencia accesible.** La UI permite navegar a la evidencia de cada corrida: logs, JSON de resultados, hashes de invariantes.

E-4. **Acciones seguras.** La UI no permite ejecutar acciones que el agente no tenga autorizadas. Cada accion se valida contra las autorizaciones vigentes.

E-5. **Documentacion.** Existe un documento `docs/LAB_UI.md` que describe la UI, las acciones disponibles, las autorizaciones vigentes y como interpretar los estados.

E-6. **Suite en verde.** La suite cubre la UI y las acciones expuestas.

E-7. **Sin regresiones.** El flujo sin UI sigue intacto. La UI es un envoltorio del flujo, no una reimplementacion.

E-8. **Encaje con el objetivo final.** La UI sirve al objetivo declarado del laboratorio controlado con flujos validados sobre dispositivos fisicos, red residencial, integracion con modelo de vision y escalado por etapas.
