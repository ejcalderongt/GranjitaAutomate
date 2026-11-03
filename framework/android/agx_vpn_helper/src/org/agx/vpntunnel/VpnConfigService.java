// PROPIEDAD INTELECTUAL - AGX FRAMEWORK | MOTOR TUNEL CONVERSOR TUN-A-HTTP-CONNECT
package org.agx.vpntunnel;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Intent;
import android.net.VpnService;
import android.os.ParcelFileDescriptor;
import android.util.Log;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.Collections;
import org.json.JSONArray;
import org.json.JSONObject;

/** Control y ciclo de vida. Un motor TCP compatible debe suministrarse por separado. */
public final class VpnConfigService extends VpnService implements Runnable {
    private static final String TAG = "AGX-TUNIC";
    public static volatile VpnConfigService instance;
    public static volatile String phase = "stopped";
    private volatile Thread worker;
    private volatile ParcelFileDescriptor tun;
    private volatile PacketEngine engine;
    private volatile HttpConnectTransport transport;
    private String host;
    private int port;
    private final Object resources = new Object();

    @Override public void onCreate() {
        super.onCreate();
        instance = this;
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        closeResources();
        Thread old = worker;
        if (old != null) {
            old.interrupt();
            try { old.join(2000); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
            if (old.isAlive()) { phase = "previous_worker_pending"; stopSelf(startId); return START_NOT_STICKY; }
        }
        android.content.SharedPreferences config = getSharedPreferences("endpoint", MODE_PRIVATE);
        host = intent != null && intent.hasExtra("host") ? intent.getStringExtra("host") : config.getString("host", null);
        port = intent != null && intent.hasExtra("port") ? intent.getIntExtra("port", 0) : config.getInt("port", 0);
        if (!validHost(host) || port < 1 || port > 65535) {
            phase = "invalid_endpoint"; stopSelf(startId); return START_NOT_STICKY;
        }
        if (VpnService.prepare(this) != null) {
            phase = "consent_required"; stopSelf(startId); return START_NOT_STICKY;
        }
        config.edit().putString("host", host).putInt("port", port).apply();
        if (!engineAvailable()) { phase = "tcp_engine_missing"; stopSelf(startId); return START_NOT_STICKY; }
        NotificationManager manager = (NotificationManager)getSystemService(NOTIFICATION_SERVICE);
        manager.createNotificationChannel(new NotificationChannel("agx-vpn", "AGX VPN", NotificationManager.IMPORTANCE_LOW));
        PendingIntent settings = PendingIntent.getActivity(this, 0,
            new Intent(this, ConsentActivity.class), PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        startForeground(1, new Notification.Builder(this, "agx-vpn")
            .setSmallIcon(android.R.drawable.stat_sys_warning).setContentTitle("AGX VPN de laboratorio")
            .setContentText("Estado del transporte disponible en el panel").setContentIntent(settings).build());
        worker = new Thread(this, "AGX-TUN-TCP");
        worker.start();
        return START_STICKY;
    }

    private static boolean validHost(String value) {
        if (value == null || !value.matches("[0-9]{1,3}(\\.[0-9]{1,3}){3}")) return false;
        for (String part : value.split("\\.")) if (Integer.parseInt(part) > 255) return false;
        return true;
    }

    @Override public void run() {
        try {
            // No abrir una TUN sin un stack TCP que pueda devolver paquetes válidos.
            Class<?> implementation;
            try { implementation = Class.forName("org.agx.vpntunnel.transport.HttpConnectTcpEngine"); }
            catch (ClassNotFoundException e) { phase = "tcp_engine_missing"; return; }
            PacketEngine candidate = (PacketEngine)implementation.getDeclaredConstructor().newInstance();
            synchronized (resources) {
                engine = candidate;
                transport = new HttpConnectTransport(this::protect, host, port);
                tun = new Builder().setSession("AGX-HttpConnect-Lockdown").setMtu(1500)
                    .addAddress("10.8.0.2", 24).addRoute("0.0.0.0", 0)
                    .addAddress("fd00:8::2", 128).addRoute("::", 0)
                    .addDnsServer("8.8.8.8").setBlocking(true).establish();
                if (tun == null) throw new IllegalStateException("Consentimiento revocado o TUN no disponible");
                phase = "tun_established";
            }
            candidate.run(tun, transport);
        } catch (Exception e) {
            phase = "engine_error";
            Log.e(TAG, "Motor detenido: " + e.getClass().getSimpleName());
        } finally {
            closeResources();
            stopForeground(true);
            stopSelf();
        }
    }

    private void closeResources() {
        synchronized (resources) {
            if (tun != null) { try { tun.close(); } catch (Exception ignored) { } tun = null; }
            if (transport != null) { transport.close(); transport = null; }
            if (engine != null) { try { engine.close(); } catch (Exception ignored) { } engine = null; }
        }
    }

    public JSONObject status(String nonce) throws Exception {
        JSONObject result = baseStatus(this, nonce);
        boolean active = tun != null && worker != null && worker.isAlive();
        result.put("host", host).put("port", port).put("vpn_active", active)
            .put("always_on", isAlwaysOn()).put("lockdown", isLockdownEnabled())
            .put("interface", active ? interfaceName() : "")
            .put("routes", active ? new JSONArray(new String[]{"0.0.0.0/0", "::/0"}) : new JSONArray())
            .put("ipv6_blocked", active).put("dns_protected", false).put("probe_through_vpn", false)
            .put("public_ip", "");
        PacketEngine current = engine;
        if (active && current != null) {
            String ip = current.verifiedPublicIp();
            boolean dns = current.dnsOverTcpVerified();
            result.put("dns_protected", dns).put("public_ip", ip == null ? "" : ip)
                .put("probe_through_vpn", ip != null && !ip.isEmpty() && dns);
        }
        return result;
    }

    public static JSONObject baseStatus(android.content.Context context, String nonce) throws Exception {
        return new JSONObject().put("nonce", nonce).put("package", "org.agx.vpntunnel")
            .put("consent_granted", VpnService.prepare(context) == null).put("phase", phase)
            .put("vpn_active", false).put("always_on", false).put("lockdown", false)
            .put("engine_available", engineAvailable()).put("build_profile", "control_plane_only");
    }
    private static boolean engineAvailable() {
        try { return PacketEngine.class.isAssignableFrom(Class.forName("org.agx.vpntunnel.transport.HttpConnectTcpEngine", false, VpnConfigService.class.getClassLoader())); }
        catch (ClassNotFoundException | LinkageError e) { return false; }
    }
    private String interfaceName() throws Exception {
        for (NetworkInterface item : Collections.list(NetworkInterface.getNetworkInterfaces()))
            for (InetAddress address : Collections.list(item.getInetAddresses()))
                if ("10.8.0.2".equals(address.getHostAddress())) return item.getName();
        return "";
    }
    @Override public void onRevoke() { closeResources(); stopSelf(); }
    @Override public void onDestroy() {
        closeResources();
        Thread old = worker;
        if (old != null) old.interrupt();
        if (instance == this) instance = null;
        super.onDestroy();
    }
}
