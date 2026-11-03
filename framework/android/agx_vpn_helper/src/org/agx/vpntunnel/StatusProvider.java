// PROPIEDAD INTELECTUAL - AGX FRAMEWORK | ESTADO AUDITABLE DEL HELPER
package org.agx.vpntunnel;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.net.Uri;
import android.os.Binder;
import android.os.Bundle;
import android.os.Process;

public final class StatusProvider extends ContentProvider {
    @Override public boolean onCreate() { return true; }
    @Override public Bundle call(String method, String arg, Bundle extras) {
        if (Binder.getCallingUid() != Process.myUid())
            getContext().enforceCallingPermission("android.permission.DUMP", "AGX status requires DUMP");
        if (!"status".equals(method) || extras == null) throw new IllegalArgumentException("status required");
        String nonce = extras.getString("nonce", "");
        if (!nonce.matches("[0-9a-f]{32}")) throw new IllegalArgumentException("nonce required");
        try {
            VpnConfigService service = VpnConfigService.instance;
            Bundle result = new Bundle();
            result.putString("status", (service == null ? VpnConfigService.baseStatus(getContext(), nonce) : service.status(nonce)).toString());
            return result;
        } catch (Exception e) { throw new IllegalStateException("Status unavailable", e); }
    }
    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] args, String order) { throw new UnsupportedOperationException(); }
    @Override public String getType(Uri uri) { return "application/json"; }
    @Override public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException(); }
    @Override public int delete(Uri uri, String selection, String[] args) { throw new UnsupportedOperationException(); }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] args) { throw new UnsupportedOperationException(); }
}
