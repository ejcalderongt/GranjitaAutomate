// PROPIEDAD INTELECTUAL - AGX FRAMEWORK | CONTRATO DEL MOTOR TCP L3
package org.agx.vpntunnel;

import android.os.ParcelFileDescriptor;

/** El motor debe mantener sesiones TCP, ACK, ventanas, checksums y temporizadores. */
public interface PacketEngine extends AutoCloseable {
    void run(ParcelFileDescriptor tun, HttpConnectTransport transport) throws Exception;
    /** Sondeo HTTPS realizado por el motor a través de la TUN, nunca por un socket protegido. */
    String verifiedPublicIp();
    boolean dnsOverTcpVerified();
    void close() throws Exception;
}
