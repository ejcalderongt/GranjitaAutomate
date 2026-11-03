"""Comprobaciones de red con resultado durable, incluso sin respuesta del proxy."""
import ipaddress
import time


def verificar_proxy_auditable(database,allocator,run_id,device_id,endpoint,*,
                             leer_configuracion,consultar_salida,expected_ip=None,
                             before_confirm=lambda ip:None,
                             alcance='Android: configuración + HTTPS explícito bajo firewall; no acredita tráfico de TikTok'):
    started=time.perf_counter()
    stage='reserva'
    observed=None
    try:
        if not allocator.validar(device_id,run_id,endpoint):
            raise ValueError('Reserva no disponible')
        stage='configuracion'
        if leer_configuracion().strip()!=endpoint:
            raise ValueError('Configuración de proxy no coincide')
        database.auditar_proxy(run_id,device_id,endpoint,stage,'confirmado',alcance=alcance)
        stage='salida_https'
        observed=str(ipaddress.ip_address(consultar_salida().strip()))
        before_confirm(observed)
        if expected_ip and observed!=expected_ip:
            raise ValueError('Salida diferente de la esperada')
        allocator.confirmar_salida(device_id,run_id,observed)
        database.auditar_proxy(run_id,device_id,endpoint,stage,'confirmado',
            ip_esperada=expected_ip,ip_observada=observed,
            latencia_ms=round((time.perf_counter()-started)*1000,2),alcance=alcance)
        return observed
    except Exception as exc:
        database.auditar_proxy(run_id,device_id,endpoint,stage,'fallido',
            ip_esperada=expected_ip,ip_observada=observed,
            latencia_ms=round((time.perf_counter()-started)*1000,2),error_tipo=type(exc).__name__,alcance=alcance)
        raise
