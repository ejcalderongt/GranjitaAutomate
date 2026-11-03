"""Consentimiento explícitamente autorizado de cookies, sin gestionar autenticación."""
import asyncio
import logging
import re

log = logging.getLogger('qa.poc')
ACCEPT = re.compile(r'^(accept all(?: cookies)?|allow all(?: cookies)?|aceptar(?: todas| todo| todas las cookies)?|aceptar cookies|tout accepter)$', re.I)
COOKIE = re.compile(r'cookies?|consentimiento de cookies', re.I)


async def gestionar_pantallas_previas_ue(page, *, cancellation_event=None):
    """Máximo cinco segundos para observar, aceptar una vez y confirmar cierre.

    Solo botones en diálogos de cookies identificados. No pulsa botones Accept
    genéricos del documento ni acepta otros permisos. No acredita que haya feed.
    Ausencia, cambio de DOM y timeout son resultados, no errores de sesión.
    """
    clicked = False
    try:
        async with asyncio.timeout(5):
            while True:
                if cancellation_event is not None and cancellation_event.is_set():
                    return 'cancelado'
                dialogs = page.locator('[role="dialog"], [data-e2e="cookie-banner"], [data-e2e="cookie-consent"]')
                matches = dialogs.filter(has_text=COOKIE)
                for i in range(await matches.count()):
                    dialog = matches.nth(i)
                    if not await dialog.is_visible():
                        continue
                    button = dialog.get_by_role('button', name=ACCEPT)
                    if await button.count() != 1 or not await button.is_visible():
                        continue
                    # Una sola tentativa; un timeout no autoriza repetir el clic.
                    clicked = True
                    await button.click(timeout=1000)
                    await dialog.wait_for(state='hidden', timeout=4000)
                    return 'aceptado'
                await asyncio.sleep(.1)
    except TimeoutError:
        return 'pendiente' if clicked else 'no_detectado'
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.warning('Consentimiento no confirmado (%s)', type(exc).__name__)
        return 'pendiente'
