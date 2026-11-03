// PROPIEDAD INTELECTUAL - AGX FRAMEWORK | CONSENTIMIENTO VPN DEL SISTEMA
package org.agx.vpntunnel;

import android.app.Activity;
import android.content.Intent;
import android.net.VpnService;
import android.os.Bundle;
import android.widget.TextView;

public final class ConsentActivity extends Activity {
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        TextView message = new TextView(this);
        message.setText("AGX VPN Lockdown Helper: autorización de VPN. El motor TCP debe validarse por separado.");
        setContentView(message);
        if (saved != null) return;
        Intent request = VpnService.prepare(this);
        if (request != null) startActivityForResult(request, 1);
        else finish();
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        finish();
    }
}
