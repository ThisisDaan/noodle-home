package app.noodle.ui

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import app.noodle.NoodleViewModel

private class Bridge(private val onSettings: () -> Unit) {
    @JavascriptInterface
    fun openSettings() { Handler(Looper.getMainLooper()).post(onSettings) }
}

/** The Noodle web interface, so the app and the browser are the same thing. The login token is traded for a cookie. */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun WebScreen(vm: NoodleViewModel, openSettings: () -> Unit) {
    var canGoBack by remember { mutableStateOf(false) }
    var web by remember { mutableStateOf<WebView?>(null) }
    BackHandler(enabled = canGoBack) { web?.goBack() }

    AndroidView(
        modifier = Modifier.fillMaxSize().systemBarsPadding(),
        factory = { ctx ->
            val base = Uri.parse(vm.prefs.baseUrl)
            // Debug builds can be inspected from a computer (chrome://inspect, or adb forward + DevTools protocol).
            if (ctx.applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE != 0) {
                WebView.setWebContentsDebuggingEnabled(true)
            }
            WebView(ctx).apply {
                // match_parent, not the wrap_content that Compose gives a view by default: a WebView that wraps its
                // content has no viewport height, so vh/dvh units are 0 and every dialog or sheet limited by them collapses.
                layoutParams = android.view.ViewGroup.LayoutParams(
                    android.view.ViewGroup.LayoutParams.MATCH_PARENT, android.view.ViewGroup.LayoutParams.MATCH_PARENT,
                )
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                addJavascriptInterface(Bridge(openSettings), "NoodleApp")
                webViewClient = object : WebViewClient() {
                    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                        val u = request.url
                        if (u.host == base.host && u.port == base.port) return false
                        ctx.startActivity(Intent(Intent.ACTION_VIEW, u)) // other sites (e.g. Zigbee2MQTT) open in the browser
                        return true
                    }

                    override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) { canGoBack = view.canGoBack() }
                    override fun doUpdateVisitedHistory(view: WebView, url: String?, isReload: Boolean) { canGoBack = view.canGoBack() }

                    override fun onReceivedHttpError(view: WebView, request: WebResourceRequest, response: WebResourceResponse) {
                        // The token was revoked: back to the login screen.
                        if (request.isForMainFrame && response.statusCode == 401) vm.logout()
                    }
                }
                web = this
                // Load only once the view has a real size: a page that starts in a 0x0 WebView measures
                // vh/dvh units as 0, which collapsed every dialog and sheet that is limited by them.
                addOnLayoutChangeListener(object : android.view.View.OnLayoutChangeListener {
                    override fun onLayoutChange(v: android.view.View, l: Int, t: Int, r: Int, b: Int, ol: Int, ot: Int, or: Int, ob: Int) {
                        if (r - l > 0 && b - t > 0) {
                            v.removeOnLayoutChangeListener(this)
                            loadUrl(vm.prefs.baseUrl + "/api/auth/session", mapOf("Authorization" to "Bearer ${vm.prefs.token}"))
                        }
                    }
                })
            }
        },
        onRelease = { it.destroy(); web = null },
    )
}
