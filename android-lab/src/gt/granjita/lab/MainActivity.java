package gt.granjita.lab;

import android.app.Activity;
import android.os.Bundle;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.widget.*;

/** Entorno social local: sin permiso INTERNET, cuentas ni servicios externos. */
public class MainActivity extends Activity {
    private SharedPreferences prefs;
    private LinearLayout feed;
    private TextView status;

    private TextView text(String value, int size) {
        TextView view = new TextView(this);
        view.setText(value); view.setTextSize(size); view.setPadding(12,12,12,12);
        return view;
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("lab", MODE_PRIVATE);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL); root.setPadding(16,16,16,16);
        root.setFocusableInTouchMode(true);
        root.setBackgroundColor(Color.rgb(244,247,251));
        root.addView(text("Granjita Lab · pruebas locales",24));
        root.addView(text("Likes y comentarios permanecen en esta placa. Sin conexion a redes sociales.",15));
        status = text("Preparado",16); status.setContentDescription("lab_status");
        root.addView(status);
        ScrollView scroll = new ScrollView(this); scroll.setContentDescription("lab_feed");
        feed = new LinearLayout(this); feed.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(feed);
        root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        final EditText comment = new EditText(this); comment.setSingleLine(true);
        comment.setHint("Comentario de prueba para publicacion 01"); comment.setContentDescription("lab_comment_01");
        root.addView(comment);
        final TextView saved = text(prefs.getString("comment_01","Sin comentario guardado"),16);
        saved.setContentDescription("lab_saved_01");
        Button send = new Button(this); send.setText("Guardar comentario local"); send.setContentDescription("lab_send_01");
        send.setOnClickListener(v -> {
            String value=comment.getText().toString();
            prefs.edit().putString("comment_01",value).apply(); saved.setText(value);
            status.setText("Comentario local guardado 01");
        });
        root.addView(send); root.addView(saved);
        setContentView(root);
        for(int i=1;i<=12;i++) addCard(i);
        root.requestFocus();
        scroll.post(() -> scroll.scrollTo(0,0));
    }

    private void addCard(final int index) {
        final String suffix = String.format(java.util.Locale.US,"%02d",index);
        LinearLayout card = new LinearLayout(this); card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(12,18,12,28);
        card.addView(text("Publicacion de prueba " + suffix + " · Hoy completamos una prueba del laboratorio.",20));
        final Button like = new Button(this); like.setContentDescription("lab_like_" + suffix);
        like.setText(prefs.getBoolean("like_"+suffix,false)?"Me gusta: SI":"Me gusta: NO");
        like.setOnClickListener(v -> {
            // La operacion es establecer, no alternar: repetirla no deshace el resultado.
            prefs.edit().putBoolean("like_"+suffix,true).apply();
            like.setText("Me gusta: SI"); status.setText("Like local verificado " + suffix);
        });
        card.addView(like);
        feed.addView(card);
    }
}
