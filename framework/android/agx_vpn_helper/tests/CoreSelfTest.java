package org.agx.vpntunnel;

import java.io.DataInputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.atomic.AtomicInteger;

public final class CoreSelfTest {
    private static void require(boolean value) { if (!value) throw new AssertionError(); }
    public static void main(String[] args) throws Exception {
        byte[] packet = new byte[40]; packet[0] = 0x45; packet[3] = 40; packet[9] = 6; packet[32] = 0x50;
        require(PacketPolicy.allowTcp(packet, 40));
        packet[9] = 17; require(!PacketPolicy.allowTcp(packet, 40));
        packet[9] = 6; packet[6] = 0x20; require(!PacketPolicy.allowTcp(packet, 40));
        require(!PacketPolicy.allowTcp(new byte[2], 2));
        try (ServerSocket localServer = new ServerSocket(0); ServerSocket remoteServer = new ServerSocket(0);
             Socket client = new Socket("127.0.0.1", localServer.getLocalPort());
             Socket local = localServer.accept(); Socket proxy = new Socket("127.0.0.1", remoteServer.getLocalPort());
             Socket remote = remoteServer.accept()) {
            client.setSoTimeout(3000); remote.setSoTimeout(3000);
            ExecutorService pool = Executors.newFixedThreadPool(2);
            try (StreamBridge bridge = StreamBridge.bridgeStreams(local, proxy, pool)) {
                client.getOutputStream().write(new byte[]{1,2,3}); client.shutdownOutput();
                byte[] upload = new byte[3]; new DataInputStream(remote.getInputStream()).readFully(upload);
                require(upload[0] == 1 && upload[2] == 3);
                remote.getOutputStream().write(new byte[]{4,5}); remote.shutdownOutput();
                require(client.getInputStream().read() == 4 && client.getInputStream().read() == 5);
                require(client.getInputStream().read() == -1);
            } finally { pool.shutdownNow(); }
        }
        AtomicInteger protectedSockets = new AtomicInteger();
        try (ServerSocket server = new ServerSocket(0)) {
            Thread peer = new Thread(() -> {
                try (Socket socket = server.accept()) {
                    socket.setSoTimeout(3000);
                    StringBuilder header = new StringBuilder();
                    while (!header.toString().endsWith("\r\n\r\n")) {
                        int b = socket.getInputStream().read();
                        if (b < 0) throw new AssertionError();
                        header.append((char)b);
                    }
                    require(header.toString().startsWith("CONNECT 1.1.1.1:443 HTTP/1.1\r\n"));
                    socket.getOutputStream().write("HTTP/1.1 200 Connection Established\r\n\r\nready".getBytes(StandardCharsets.US_ASCII));
                } catch (Exception e) { throw new RuntimeException(e); }
            });
            peer.start();
            try (HttpConnectTransport transport = new HttpConnectTransport(socket -> { protectedSockets.incrementAndGet(); return true; },"127.0.0.1",server.getLocalPort());
                 Socket connected = transport.connect("1.1.1.1",443)) {
                require(connected.getInputStream().read() == 'r');
                require(protectedSockets.get() == 1);
            }
            peer.join(4000); require(!peer.isAlive());
        }
        System.out.println("Java core: PacketPolicy, duplex StreamBridge and HTTP CONNECT OK");
    }
}
