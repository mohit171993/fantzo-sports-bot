package com.fantzo.tvtrial;

import android.accessibilityservice.AccessibilityService;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.TextUtils;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class DiamondAutofillService extends AccessibilityService {
    private static final String TARGET_PACKAGE = "com.diamond.diamondlive";
    private final Handler handler = new Handler(Looper.getMainLooper());
    private long lastAttempt = 0L;

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null || event.getPackageName() == null) return;
        if (!TARGET_PACKAGE.contentEquals(event.getPackageName())) return;

        long now = System.currentTimeMillis();
        if (now - lastAttempt < 900) return;
        lastAttempt = now;
        handler.postDelayed(this::tryFillLogin, 350);
    }

    @Override
    public void onInterrupt() {
    }

    private void tryFillLogin() {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return;

        List<AccessibilityNodeInfo> editable = new ArrayList<>();
        collectEditable(root, editable);
        if (editable.isEmpty()) return;

        AccessibilityNodeInfo userNode = null;
        AccessibilityNodeInfo passNode = null;

        for (AccessibilityNodeInfo node : editable) {
            String signature = signature(node);
            if (passNode == null && containsAny(signature, "password", "passwd", "passcode", "pwd")) {
                passNode = node;
            } else if (userNode == null && containsAny(signature, "username", "user name", "login", "email", "mobile", "account")) {
                userNode = node;
            }
        }

        if (userNode == null && editable.size() >= 1) userNode = editable.get(0);
        if (passNode == null && editable.size() >= 2) passNode = editable.get(1);
        if (userNode == null || passNode == null || userNode == passNode) return;

        boolean userSet = setText(userNode, BuildConfig.DIAMOND_USERNAME);
        boolean passSet = setText(passNode, BuildConfig.DIAMOND_PASSWORD);
        if (userSet && passSet) {
            handler.postDelayed(() -> clickLogin(root), 500);
        }
    }

    private void collectEditable(AccessibilityNodeInfo node, List<AccessibilityNodeInfo> out) {
        if (node == null) return;
        CharSequence cls = node.getClassName();
        String className = cls == null ? "" : cls.toString();
        if (node.isEditable() || className.contains("EditText")) {
            out.add(node);
        }
        for (int i = 0; i < node.getChildCount(); i++) {
            collectEditable(node.getChild(i), out);
        }
    }

    private String signature(AccessibilityNodeInfo node) {
        StringBuilder sb = new StringBuilder();
        append(sb, node.getViewIdResourceName());
        append(sb, node.getText());
        append(sb, node.getContentDescription());
        append(sb, node.getHintText());
        return sb.toString().toLowerCase(Locale.US);
    }

    private void append(StringBuilder sb, Object value) {
        if (value != null) sb.append(' ').append(value);
    }

    private boolean containsAny(String text, String... terms) {
        for (String term : terms) if (text.contains(term)) return true;
        return false;
    }

    private boolean setText(AccessibilityNodeInfo node, String value) {
        if (node == null || TextUtils.isEmpty(value)) return false;
        Bundle args = new Bundle();
        args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value);
        node.performAction(AccessibilityNodeInfo.ACTION_FOCUS);
        return node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
    }

    private void clickLogin(AccessibilityNodeInfo root) {
        AccessibilityNodeInfo candidate = findLoginNode(root);
        if (candidate == null) return;
        AccessibilityNodeInfo clickable = candidate;
        while (clickable != null && !clickable.isClickable()) {
            clickable = clickable.getParent();
        }
        if (clickable != null) clickable.performAction(AccessibilityNodeInfo.ACTION_CLICK);
    }

    private AccessibilityNodeInfo findLoginNode(AccessibilityNodeInfo node) {
        if (node == null) return null;
        StringBuilder sb = new StringBuilder();
        append(sb, node.getText());
        append(sb, node.getContentDescription());
        String text = sb.toString().trim().toLowerCase(Locale.US);
        if (text.equals("login") || text.equals("log in") || text.equals("sign in") || text.equals("signin")) {
            return node;
        }
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo found = findLoginNode(node.getChild(i));
            if (found != null) return found;
        }
        return null;
    }
}
