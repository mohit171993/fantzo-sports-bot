package com.fantzo.tvtrial;

import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.accessibility.AccessibilityManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.util.List;

public class MainActivity extends Activity {
    private static final String TARGET_PACKAGE = "com.diamond.diamondlive";
    private TextView status;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(48, 64, 48, 48);
        root.setGravity(Gravity.CENTER_HORIZONTAL);

        TextView title = new TextView(this);
        title.setText("Fantzo TV Trial");
        title.setTextSize(26f);
        title.setGravity(Gravity.CENTER_HORIZONTAL);
        root.addView(title);

        status = new TextView(this);
        status.setTextSize(16f);
        status.setPadding(0, 32, 0, 32);
        root.addView(status);

        Button enable = new Button(this);
        enable.setText("1. Enable Fantzo TV Login Helper");
        enable.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)));
        root.addView(enable);

        Button open = new Button(this);
        open.setText("2. Open Diamond Live");
        open.setOnClickListener(v -> launchDiamond());
        root.addView(open);

        TextView note = new TextView(this);
        note.setPadding(0, 28, 0, 0);
        note.setText("Trial only. The helper is restricted to Diamond Live and fills the configured login on that app's login screen.");
        root.addView(note);

        setContentView(root);
        refreshStatus();

        if (getIntent() != null && getIntent().getData() != null && "fantzotv".equals(getIntent().getData().getScheme())) {
            root.postDelayed(() -> {
                if (isHelperEnabled()) {
                    launchDiamond();
                }
            }, 400);
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (status != null) refreshStatus();
    }

    private void refreshStatus() {
        if (isHelperEnabled()) {
            status.setText("✅ Login helper enabled. Tap Open Diamond Live.");
        } else {
            status.setText("⚠️ First-time setup: enable Fantzo TV Trial in Accessibility settings, then return here.");
        }
    }

    private boolean isHelperEnabled() {
        AccessibilityManager manager = (AccessibilityManager) getSystemService(Context.ACCESSIBILITY_SERVICE);
        if (manager == null) return false;
        List<AccessibilityServiceInfo> enabled = manager.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK);
        String expected = getPackageName() + "/" + DiamondAutofillService.class.getName();
        for (AccessibilityServiceInfo info : enabled) {
            if (info.getId() != null && (info.getId().equals(expected) || info.getId().contains(getPackageName()))) {
                return true;
            }
        }
        return false;
    }

    private void launchDiamond() {
        if (!isHelperEnabled()) {
            Toast.makeText(this, "Enable the Fantzo TV Login Helper first.", Toast.LENGTH_LONG).show();
            startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
            return;
        }

        Intent intent = getPackageManager().getLaunchIntentForPackage(TARGET_PACKAGE);
        if (intent == null) {
            Toast.makeText(this, "Diamond Live is not installed on this phone.", Toast.LENGTH_LONG).show();
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, android.net.Uri.parse("market://details?id=" + TARGET_PACKAGE)));
            } catch (Exception ignored) {
                startActivity(new Intent(Intent.ACTION_VIEW, android.net.Uri.parse("https://play.google.com/store/apps/details?id=" + TARGET_PACKAGE)));
            }
            return;
        }
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        startActivity(intent);
    }
}
