package org.panda.qa;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.URL;
import javax.net.ssl.HttpsURLConnection;

/** Network probe only: fixed HTTPS destination, explicit proxy, platform TLS trust. */
public final class EgressProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 2 || !args[0].matches("[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+")) {
            throw new IllegalArgumentException("IPv4 proxy and port required");
        }
        int port = Integer.parseInt(args[1]);
        if (port < 1 || port > 65535) throw new IllegalArgumentException("Invalid port");
        Proxy proxy = new Proxy(Proxy.Type.HTTP, new InetSocketAddress(args[0], port));
        HttpsURLConnection connection = (HttpsURLConnection) new URL("https://api.ipify.org").openConnection(proxy);
        connection.setConnectTimeout(10000);
        connection.setReadTimeout(10000);
        connection.setInstanceFollowRedirects(false);
        try {
            if (connection.getResponseCode() != 200) throw new IllegalStateException("HTTPS response not 200");
            ByteArrayOutputStream body = new ByteArrayOutputStream();
            try (InputStream stream = connection.getInputStream()) {
                int value;
                while ((value = stream.read()) != -1) {
                    if (body.size() >= 80) throw new IllegalStateException("Oversized response");
                    body.write(value);
                }
            }
            String ip = body.toString("UTF-8").trim();
            if (!ip.matches("[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+")) throw new IllegalStateException("Invalid IP response");
            System.out.println("PANDA_EGRESS_IP=" + ip);
        } finally {
            connection.disconnect();
        }
    }
}
