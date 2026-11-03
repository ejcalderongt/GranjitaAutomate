"""Lectura acotada de metadatos del contenedor de video activo."""
import logging

logger = logging.getLogger('warmer.scraper')
SELECTORES_VIDEO = {
    'autor': "h3[data-e2e='video-author-uniqueid']",
    'descripcion': "div[data-e2e='video-desc']",
    'sonido_original': "div[data-e2e='video-music']",
}
LIMITES = {'autor': 200, 'descripcion': 4000, 'sonido_original': 500}
DEFAULTS = {'autor': 'Desconocido', 'descripcion': 'Sin descripción', 'sonido_original': 'Desconocido'}


def extraer_contexto_video(page, *, scope=None, selectors=None, aviso=lambda **kwargs: None):
    """scope evita mezclar metadatos de videos precargados fuera del activo."""
    root = scope if scope is not None else page
    result = dict(DEFAULTS)
    for field, selector in {**SELECTORES_VIDEO, **(selectors or {})}.items():
        if field not in result:
            continue
        try:
            element = root.locator(selector).first
            if element.is_visible():
                value = element.inner_text(timeout=1500).strip()
                if value:
                    result[field] = value[:LIMITES[field]]
        except Exception as exc:
            aviso(campo=field, error_type=type(exc).__name__)
    return result


async def extraer_contexto_video_movil(page, *, scope=None, selectors=None, aviso=lambda **kwargs: None):
    """Variante async para Page/Locator asíncronos, sin capturas de pantalla."""
    root = scope if scope is not None else page
    result = dict(DEFAULTS)
    for field, selector in {**SELECTORES_VIDEO, **(selectors or {})}.items():
        if field not in result:
            continue
        try:
            element = root.locator(selector).first
            if await element.is_visible():
                value = (await element.inner_text(timeout=1500)).strip()
                if value:
                    result[field] = value[:LIMITES[field]]
        except Exception as exc:
            logger.warning('Metadato no disponible: %s (%s)', field, type(exc).__name__)
            aviso(campo=field, error_type=type(exc).__name__)
    return result
