// PROPIEDAD INTELECTUAL - AGX FRAMEWORK | CONTROL ADB CON PERMISO DUMP
package org.agx.vpntunnel;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** El permiso DUMP del manifiesto restringe la entrada ADB; no exportar un control sin permiso. */
public final class ControlReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        String operation = intent.getStringExtra("operation");
        Intent service = new Intent(context, VpnConfigService.class);
        if ("stop".equals(operation)) context.stopService(service);
        else if ("start".equals(operation)) {
            service.putExtra("host", intent.getStringExtra("host"));
            service.putExtra("port", intent.getIntExtra("port", 0));
            context.startForegroundService(service);
        }
    }
}
