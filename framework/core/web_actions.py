"""Gestos táctiles de Chromium, en coordenadas CSS del viewport."""

import asyncio
import math
import random
from contextlib import suppress

from playwright.async_api import Error, Locator, Page

async def ejecutar_toque_tactil(page: Page, button: Locator) -> None:
    """Espera visibilidad, estabilidad y recepción de eventos; pulsa por CDP."""
    await button.tap(trial=True, timeout=5000)
    box = await button.bounding_box()
    if not box:
        raise ValueError('El botón desapareció antes del toque')
    session = await page.context.new_cdp_session(page)
    try:
        await session.send('Input.dispatchTouchEvent', {
            'type': 'touchStart', 'touchPoints': [{
                'x': box['x'] + box['width'] / 2,
                'y': box['y'] + box['height'] / 2, 'id': 1,
            }],
        })
        await session.send('Input.dispatchTouchEvent', {
            'type': 'touchEnd', 'touchPoints': [],
        })
    finally:
        with suppress(Error):
            await session.detach()


async def ejecutar_desplazamiento_tactil(
    page: Page, *, selector: str | None = None, rng: random.Random | None = None
) -> None:
    """Swipe ascendente; selector opcional para un panel con scroll propio.

    La variación sirve para cobertura de trayectorias; no modela fricción física.
    Los errores de CDP se propagan al orquestador después de liberar el contacto.
    """
    rng = rng or random.Random()
    viewport = await page.evaluate("({width: innerWidth, height: innerHeight})")
    left, top, right, bottom = 0.0, 0.0, viewport['width'], viewport['height']
    if selector:
        panel = page.locator(selector).filter(visible=True).first
        await panel.wait_for(state="visible", timeout=5000)
        box = await panel.bounding_box()
        if not box:
            raise ValueError("El panel de scroll no tiene dimensiones")
        left, top = max(0, box['x']), max(0, box['y'])
        right = min(right, box['x'] + box['width'])
        bottom = min(bottom, box['y'] + box['height'])
    width, height = right - left, bottom - top
    if width < 40 or height < 80:
        raise ValueError("Área visible insuficiente para un swipe")
    x = left + width * rng.uniform(0.4, 0.6)
    start_y, end_y = top + height * 0.8, top + height * 0.22
    drift = rng.uniform(-width * 0.04, width * 0.04)
    steps, duration = rng.randint(20, 32), rng.uniform(0.4, 0.7)
    session = await page.context.new_cdp_session(page)
    active = False

    async def dispatch(kind: str, px: float = x, py: float = start_y) -> None:
        points = [] if kind in ('touchEnd', 'touchCancel') else [
            {'x': px, 'y': py, 'id': 1, 'radiusX': 5, 'radiusY': 5, 'force': 0.6}
        ]
        await session.send('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': points})

    try:
        active = True
        await dispatch('touchStart')
        for step in range(1, steps + 1):
            await asyncio.sleep(duration / steps)
            t = step / steps
            eased = (1 - math.cos(math.pi * t)) / 2
            jitter = rng.uniform(-1.5, 1.5) * math.sin(math.pi * t)
            await dispatch('touchMove', x + drift * eased + jitter,
                           start_y + (end_y - start_y) * eased)
        await dispatch('touchEnd')
        active = False
    finally:
        if active:
            with suppress(Error):
                await dispatch('touchCancel')
        with suppress(Error):
            await session.detach()
