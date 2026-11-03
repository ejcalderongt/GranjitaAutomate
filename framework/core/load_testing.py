"""Temporización QA determinista, acotada y cancelable; no modela conducta humana."""
import asyncio
import logging
import math
import time

logger = logging.getLogger('qa.load_testing')


async def regular_retencion_de_carga(datos_video, tiempo_base_configurables, cancellation_event=None):
    if isinstance(tiempo_base_configurables, bool):
        raise ValueError('Tiempo base inválido')
    base = float(tiempo_base_configurables)
    if not math.isfinite(base) or not 0 <= base <= 30:
        raise ValueError('Tiempo base requiere un valor finito entre 0 y 30 segundos')
    texts = [datos_video.get(key, '') for key in ('descripcion', 'sonido_original')]
    if any(not isinstance(value, str) for value in texts):
        raise ValueError('El contexto QA debe contener texto')
    size = sum(map(len, texts))
    duration = min(30.0, base + size * .05)
    started = time.monotonic()
    state = 'completado'
    logger.info('Retención QA programada: %.3f s', duration)
    while True:
        if cancellation_event is not None and cancellation_event.is_set():
            state = 'cancelado'
            break
        remaining = duration - (time.monotonic()-started)
        if remaining <= 0:
            break
        if isinstance(cancellation_event, asyncio.Event):
            try:
                await asyncio.wait_for(cancellation_event.wait(), timeout=remaining)
            except TimeoutError:
                pass
        else:
            await asyncio.sleep(min(.05, remaining))
    return {'estado_retencion': state, 'tiempo_ejecutado': round(time.monotonic()-started,3),
            'tiempo_programado': round(duration,3), 'longitud_texto': size}
