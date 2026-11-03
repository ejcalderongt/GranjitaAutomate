import asyncio
import unittest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace

import httpx

from core.geo_resolver import obtener_geolocalizacion_con_bypass


class GeoResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_browser_boundary_does_not_nest_event_loop(self):
        from tiktok_warmer.test_connection import resolver_geo_en_worker
        expected = {'continente': 'EU', 'provider_used': 'fixture'}
        with patch('tiktok_warmer.test_connection.resolver_geo_por_proxy', new=AsyncMock(return_value=expected)):
            result = resolver_geo_en_worker('8.8.8.8', SimpleNamespace(bridge=None), {'server':'http://example.org:80'})
        self.assertEqual(result, expected)

    async def test_geo_uses_existing_loopback_proxy_and_closes_its_client(self):
        from tiktok_warmer.test_connection import resolver_geo_por_proxy
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
        runtime = SimpleNamespace(bridge=SimpleNamespace(endpoint='http://127.0.0.1:32123'))
        with patch('tiktok_warmer.test_connection.httpx.AsyncClient', return_value=client) as factory, \
             patch('tiktok_warmer.test_connection.obtener_geolocalizacion_con_bypass', new=AsyncMock(return_value={'continente':'EU'})) as resolve:
            await resolver_geo_por_proxy('8.8.8.8', runtime, {'server':'socks5://upstream:8080'})
        self.assertEqual(str(factory.call_args.kwargs['proxy'].url), 'http://127.0.0.1:32123')
        self.assertFalse(factory.call_args.kwargs['trust_env'])
        resolve.assert_awaited_once_with('8.8.8.8', cliente_http=client)
        self.assertTrue(client.is_closed)

    async def test_quota_falls_back_with_exact_ip_and_continent_field(self):
        requests = []
        def handle(request):
            requests.append(request)
            if request.url.host == 'ipapi.co':
                return httpx.Response(429)
            self.assertEqual(request.url.path, '/json/8.8.8.8')
            self.assertIn('continentCode', request.url.params['fields'])
            return httpx.Response(200, json={'query':'8.8.8.8', 'status':'success',
                'countryCode':'NO','continentCode':'EU','isp':'test'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            result = await obtener_geolocalizacion_con_bypass('8.8.8.8', client)
            self.assertFalse(client.is_closed)
        self.assertEqual(result['provider_used'], 'ip-api.com')
        self.assertEqual(result['continente'], 'EU')
        self.assertEqual(result['attempts'][0]['outcome'], 'rate_limited')
        self.assertEqual(len(requests), 2)

    async def test_malformed_and_internal_error_fall_back_to_non_eu_member(self):
        def handle(request):
            if request.url.host == 'ipapi.co':
                return httpx.Response(200, text='not JSON')
            if request.url.host == 'ip-api.com':
                return httpx.Response(200, json={'status':'fail'})
            self.assertEqual(request.url.path, '/8.8.8.8/json')
            return httpx.Response(200, json={'ip':'8.8.8.8','country':'GB','org':'test'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            result = await obtener_geolocalizacion_con_bypass('8.8.8.8', client)
        self.assertEqual(result['continente'], 'EU')
        self.assertEqual(result['provider_used'], 'ipinfo.io')

    async def test_valid_non_european_result_does_not_hunt_for_europe(self):
        requests = []
        def handle(request):
            requests.append(request)
            return httpx.Response(200, json={'ip':'8.8.8.8','country_code':'US','continent_code':'NA'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            result = await obtener_geolocalizacion_con_bypass('8.8.8.8', client)
        self.assertEqual(result['continente'], 'NA')
        self.assertEqual(len(requests), 1)

    async def test_all_fail_reports_unknown_with_each_attempt(self):
        async def handle(request):
            await asyncio.sleep(0)
            raise httpx.ConnectTimeout('do not persist raw exception', request=request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            result = await obtener_geolocalizacion_con_bypass('8.8.8.8', client)
        self.assertEqual(result['provider_used'], 'FAILED_ALL')
        self.assertEqual(result['continente'], 'UNKNOWN')
        self.assertEqual(len(result['attempts']), 3)
        self.assertNotIn('do not persist raw exception', str(result))

    async def test_wrong_ip_and_ambiguous_country_are_not_certified(self):
        def handle(request):
            if request.url.host == 'ipapi.co':
                return httpx.Response(200, json={'ip':'1.1.1.1','country_code':'FR','continent_code':'EU'})
            if request.url.host == 'ip-api.com':
                return httpx.Response(503)
            return httpx.Response(200, json={'ip':'8.8.8.8','country':'RU'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            result = await obtener_geolocalizacion_con_bypass('8.8.8.8', client)
        self.assertEqual(result['geo_status'], 'unavailable')

    async def test_owned_client_is_closed_and_invalid_ip_never_queries(self):
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
            httpx.Response(200, json={'ip':'8.8.8.8','country_code':'CH','continent_code':'EU'})))
        with patch('core.geo_resolver.httpx.AsyncClient', return_value=client):
            result = await obtener_geolocalizacion_con_bypass('8.8.8.8')
        self.assertTrue(client.is_closed)
        self.assertEqual(result['continente'], 'EU')
        with patch('core.geo_resolver.httpx.AsyncClient') as factory:
            with self.assertRaises(ValueError):
                await obtener_geolocalizacion_con_bypass('8.8.8.8/path')
            with self.assertRaises(ValueError):
                await obtener_geolocalizacion_con_bypass('127.0.0.1')
            factory.assert_not_called()
