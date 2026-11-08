"""Puente HTTP de loopback a SOCKS5 autenticado; vida útil ligada al navegador."""
import asyncio
import threading


class SocksBridge:
    def __init__(self, server, username, password):
        self.server = server
        self.username = username
        self.password = password
        self.loop = None
        self.thread = None
        self.ready = threading.Event()
        self.endpoint = None
        self.error = False

    def start(self):
        def run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            listener = None
            transports = set()
            closing = False
            create_server = self.loop.create_server

            async def tracked_server(factory, *args, **kwargs):
                def tracked_factory():
                    protocol = factory()
                    connected = protocol.connection_made
                    disconnected = protocol.connection_lost
                    owned = []
                    def connection_made(transport):
                        transports.add(transport)
                        owned.append(transport)
                        connected(transport)
                        if closing:
                            transport.abort()
                    def connection_lost(exc):
                        for transport in owned:
                            transports.discard(transport)
                        owned.clear()
                        disconnected(exc)
                    protocol.connection_made = connection_made
                    protocol.connection_lost = connection_lost
                    return protocol
                return await create_server(tracked_factory, *args, **kwargs)

            self.loop.create_server = tracked_server
            try:
                import pproxy
                remote = pproxy.Connection(self.server)
                remote.users = [(self.username + ':' + self.password).encode()]
                local = pproxy.Server('http://127.0.0.1:0')
                listener = self.loop.run_until_complete(local.start_server({'rserver': [remote]}))
                self.endpoint = 'http://127.0.0.1:' + str(listener.sockets[0].getsockname()[1])
                self.ready.set()
                self.loop.run_forever()
            except Exception:
                self.error = True
                self.ready.set()
            finally:
                closing = True
                if listener:
                    listener.close()
                # Server.wait_closed can wait for clients still stuck in a handshake.
                # Close owned accepted transports before waiting for their handlers.
                for transport in list(transports):
                    transport.abort()
                tasks = asyncio.all_tasks(self.loop)
                for task in tasks:
                    task.cancel()
                if tasks:
                    self.loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                if listener:
                    self.loop.run_until_complete(listener.wait_closed())
                self.loop.run_until_complete(self.loop.shutdown_asyncgens())
                self.loop.close()
        self.thread = threading.Thread(target=run, name='socks5-browser-bridge', daemon=True)
        self.thread.start()
        if not self.ready.wait(10) or self.error:
            self.close()
            raise RuntimeError('No se pudo iniciar el puente SOCKS5 local')
        return self.endpoint

    def close(self):
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self.thread:
            self.thread.join(5)
            if self.thread.is_alive():
                raise RuntimeError('El puente SOCKS5 no confirmó su cierre')


class BrowserRuntime:
    def __init__(self, runtime, bridge):
        self.runtime, self.bridge = runtime, bridge

    def __getattr__(self, name):
        return getattr(self.runtime, name)

    def stop(self):
        try:
            self.runtime.stop()
        finally:
            if self.bridge:
                self.bridge.close()


def proxy_para_chromium(options):
    if options['server'].startswith('socks5://') and options.get('username'):
        bridge = SocksBridge(options['server'], options['username'], options['password'])
        return {'server': bridge.start()}, bridge
    return options, None
