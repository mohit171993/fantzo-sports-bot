package com.windsor.dashboard;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.HttpAuthHandler;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;

public class MainActivity extends Activity {
    private static final String DASHBOARD_URL =
            "https://meta-ads-control-production.up.railway.app/windsor-login";
    private static final String PREFS = "windsor_auth";
    private static final String KEY_USER = "username";
    private static final String KEY_PASS = "password";

    private WebView webView;
    private ProgressBar progressBar;
    private boolean authDialogVisible = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.WHITE);

        webView = new WebView(this);
        webView.setBackgroundColor(Color.WHITE);

        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setMax(100);

        root.addView(webView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));

        FrameLayout.LayoutParams progressParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, 8);
        root.addView(progressBar, progressParams);

        setContentView(root);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setLoadsImagesAutomatically(true);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);

        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(webView, true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedHttpAuthRequest(
                    WebView view,
                    HttpAuthHandler handler,
                    String host,
                    String realm) {

                SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
                String savedUser = prefs.getString(KEY_USER, "");
                String savedPass = prefs.getString(KEY_PASS, "");

                if (!savedUser.isEmpty() && !savedPass.isEmpty()) {
                    handler.proceed(savedUser, savedPass);
                    return;
                }

                if (authDialogVisible) {
                    return;
                }
                authDialogVisible = true;

                final EditText userInput = new EditText(MainActivity.this);
                userInput.setHint("Username");
                userInput.setSingleLine(true);
                userInput.setText("admin");

                final EditText passInput = new EditText(MainActivity.this);
                passInput.setHint("Password");
                passInput.setSingleLine(true);
                passInput.setInputType(
                        InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);

                LinearLayout form = new LinearLayout(MainActivity.this);
                form.setOrientation(LinearLayout.VERTICAL);
                int pad = (int) (24 * getResources().getDisplayMetrics().density);
                form.setPadding(pad, pad / 2, pad, 0);
                form.addView(userInput);
                form.addView(passInput);

                AlertDialog dialog = new AlertDialog.Builder(MainActivity.this)
                        .setTitle("Windsor Login")
                        .setMessage("Enter your dashboard credentials")
                        .setView(form)
                        .setCancelable(false)
                        .setPositiveButton("Login", null)
                        .setNegativeButton("Cancel", (d, which) -> {
                            authDialogVisible = false;
                            handler.cancel();
                        })
                        .create();

                dialog.setOnShowListener(d -> {
                    dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
                        String username = userInput.getText().toString().trim();
                        String password = passInput.getText().toString();

                        if (username.isEmpty() || password.isEmpty()) {
                            if (username.isEmpty()) userInput.setError("Required");
                            if (password.isEmpty()) passInput.setError("Required");
                            return;
                        }

                        prefs.edit()
                                .putString(KEY_USER, username)
                                .putString(KEY_PASS, password)
                                .apply();

                        authDialogVisible = false;
                        handler.proceed(username, password);
                        dialog.dismiss();
                    });
                });

                dialog.setOnDismissListener(d -> authDialogVisible = false);
                dialog.show();
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progressBar.setProgress(newProgress);
                progressBar.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
            }
        });

        if (savedInstanceState == null) {
            webView.loadUrl(DASHBOARD_URL);
        } else {
            webView.restoreState(savedInstanceState);
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        webView.saveState(outState);
        super.onSaveInstanceState(outState);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            CookieManager.getInstance().flush();
            webView.destroy();
        }
        super.onDestroy();
    }
}
