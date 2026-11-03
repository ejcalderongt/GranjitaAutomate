// PROPIEDAD INTELECTUAL - AGX FRAMEWORK | POLÍTICA IPv4 TCP
package org.agx.vpntunnel;

/** Validación de paquetes; no sustituye una implementación de TCP. */
public final class PacketPolicy {
    private PacketPolicy() { }
    public static boolean allowTcp(byte[] packet, int length) {
        if (length < 40 || length > packet.length || (packet[0] >>> 4 & 15) != 4) return false;
        int ihl = (packet[0] & 15) * 4;
        int total = (packet[2] & 255) * 256 + (packet[3] & 255);
        int fragment = (packet[6] & 255) * 256 + (packet[7] & 255);
        if (ihl < 20 || ihl + 20 > length || total != length || (fragment & 0x3fff) != 0) return false;
        if ((packet[9] & 255) != 6) return false; // Incluye descarte de UDP/QUIC e ICMP.
        int tcp = ((packet[ihl + 12] >>> 4) & 15) * 4;
        return tcp >= 20 && ihl + tcp <= total;
    }
}
