// PROPIEDAD INTELECTUAL - AGX FRAMEWORK | PUENTE BIDIRECCIONAL DE STREAMS
package org.agx.vpntunnel;

import java.io.InputStream;
import java.io.OutputStream;
import java.io.IOException;
import java.net.Socket;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/** Solo para dos streams TCP establecidos; nunca escribir bytes de aplicación crudos a una TUN. */
public final class StreamBridge implements AutoCloseable {
    private final Socket local;
    private final Socket proxy;
    private final AtomicBoolean closed = new AtomicBoolean();
    private final AtomicInteger finished = new AtomicInteger();

    private StreamBridge(Socket local, Socket proxy) { this.local = local; this.proxy = proxy; }

    public static StreamBridge bridgeStreams(Socket local, Socket proxy, ExecutorService pool) throws IOException {
        StreamBridge bridge = new StreamBridge(local, proxy);
        try {
            pool.execute(() -> bridge.pump(local, proxy));
            pool.execute(() -> bridge.pump(proxy, local));
            return bridge;
        } catch (RuntimeException e) {
            bridge.close();
            throw e;
        }
    }

    private void pump(Socket source, Socket target) {
        byte[] bytes = new byte[8192];
        try {
            InputStream in = source.getInputStream();
            OutputStream out = target.getOutputStream();
            int n;
            while (!closed.get() && (n = in.read(bytes)) != -1) {
                if (n > 0) out.write(bytes, 0, n);
            }
            if (!closed.get()) target.shutdownOutput();
        } catch (IOException e) {
            close();
        } finally {
            if (finished.incrementAndGet() == 2) close();
        }
    }

    @Override public void close() {
        if (!closed.compareAndSet(false, true)) return;
        try { local.close(); } catch (IOException ignored) { }
        try { proxy.close(); } catch (IOException ignored) { }
    }
}
