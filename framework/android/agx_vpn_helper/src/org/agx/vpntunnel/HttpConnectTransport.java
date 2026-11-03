// PROPIEDAD INTELECTUAL - AGX FRAMEWORK | TRANSPORTE HTTP CONNECT PROTEGIDO
package org.agx.vpntunnel;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;
import java.util.function.Predicate;

/** Un socket por flujo establecido por el motor TCP, no un socket por paquete IP. */
public final class HttpConnectTransport implements AutoCloseable {
    private final Predicate<Socket> protector;
    private final String host;
    private final int port;
    private final Set<Socket> sockets = new HashSet<>();
    private boolean closed;
    public HttpConnectTransport(Predicate<Socket> protector, String host, int port) {
        this.protector = protector; this.host = host; this.port = port;
    }
    public Socket connect(String destinationIp, int destinationPort) throws IOException {
        if (!destinationIp.matches("[0-9a-fA-F:.]+") || destinationPort < 1 || destinationPort > 65535)
            throw new IOException("Destino literal inválido");
        String ip = InetAddress.getByName(destinationIp).getHostAddress();
        String authority = (ip.contains(":") ? "[" + ip + "]" : ip) + ":" + destinationPort;
        Socket socket = new Socket();
        synchronized (this) {
            if (closed || sockets.size() >= 64) throw new IOException("Capacidad de transporte agotada");
            sockets.add(socket);
        }
        try {
            if (!protector.test(socket)) throw new IOException("No se pudo proteger el socket de transporte");
            socket.connect(new InetSocketAddress(host, port), 10000);
            socket.setSoTimeout(10000);
            socket.getOutputStream().write(("CONNECT " + authority + " HTTP/1.1\r\nHost: " + authority + "\r\nProxy-Connection: keep-alive\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
            InputStream in = socket.getInputStream();
            ByteArrayOutputStream header = new ByteArrayOutputStream();
            int matched = 0;
            byte[] end = new byte[] {13, 10, 13, 10};
            long deadline = System.nanoTime() + 10000000000L;
            while (matched < 4) {
                if (header.size() >= 8192 || System.nanoTime() > deadline) throw new IOException("Respuesta CONNECT excedida");
                int b = in.read();
                if (b < 0) throw new IOException("CONNECT terminó sin cabeceras");
                header.write(b);
                matched = b == end[matched] ? matched + 1 : (b == 13 ? 1 : 0);
            }
            String first = new String(header.toByteArray(), StandardCharsets.US_ASCII).split("\r\n", 2)[0];
            if (!first.matches("HTTP/1\\.[01] 200(?: .*)?")) throw new IOException("CONNECT no aceptado");
            socket.setSoTimeout(0);
            return socket;
        } catch (Exception e) {
            release(socket);
            if (e instanceof IOException) throw (IOException)e;
            throw new IOException("Transporte no disponible", e);
        }
    }
    public synchronized void release(Socket socket) {
        sockets.remove(socket);
        try { socket.close(); } catch (IOException ignored) { }
    }
    @Override public synchronized void close() {
        closed = true;
        for (Socket socket : sockets) try { socket.close(); } catch (IOException ignored) { }
        sockets.clear();
    }
}
