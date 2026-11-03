/* PROPIEDAD INTELECTUAL - AGX FRAMEWORK | CONTRATO PROPUESTO, NO MOTOR */
/* Fuera de src: no se compila ni habilita la VPN.
 * Java propuesto: package org.agx.vpntunnel;
 * class Tun2SocksJNI { static native void start(int fd, String host, int port); }
 * Descriptor: (ILjava/lang/String;I)V
 * No es un contrato extraído del APK actual. */
#include <jni.h>
#include <android/log.h>

JNIEXPORT void JNICALL
Java_org_agx_vpntunnel_Tun2SocksJNI_start(
        JNIEnv *env, jclass clazz, jint tun_fd, jstring proxy_host, jint proxy_port) {
    (void)clazz;
    (void)tun_fd;
    (void)proxy_host;
    (void)proxy_port;
    __android_log_print(ANDROID_LOG_ERROR, "AGX-JNI",
                       "Motor y contrato del proveedor pendientes; inicio rechazado");
    jclass error = (*env)->FindClass(env, "java/lang/UnsupportedOperationException");
    if (error != NULL) {
        (*env)->ThrowNew(env, error, "Falta integrar el motor nativo real");
    }
}
