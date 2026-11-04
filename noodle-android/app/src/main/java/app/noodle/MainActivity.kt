package app.noodle

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.compose.BackHandler
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import app.noodle.ui.WebScreen
import app.noodle.ui.LoginScreen
import app.noodle.ui.SettingsScreen

class MainActivity : ComponentActivity() {
    private val vm: NoodleViewModel by viewModels()

    // Starting a foreground service is only allowed while the app is on screen (or from boot), so it is started here.
    override fun onStart() {
        super.onStart()
        NotifyService.sync(this)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val dark = isSystemInDarkTheme()
            val ctx = LocalContext.current
            MaterialTheme(colorScheme = if (dark) dynamicDarkColorScheme(ctx) else dynamicLightColorScheme(ctx)) {
                Surface(color = MaterialTheme.colorScheme.background) { Root(vm) }
            }
        }
    }

}

@Composable
private fun Root(vm: NoodleViewModel) {
    val loggedIn by vm.loggedIn.collectAsState()
    var settings by remember { mutableStateOf(false) }
    if (!loggedIn) {
        LoginScreen(vm)
        return
    }
    // The web interface stays composed under the settings page, so it keeps its place when you come back.
    Box(Modifier.fillMaxSize()) {
        WebScreen(vm) { settings = true }
        if (settings) {
            BackHandler { settings = false }
            Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                SettingsScreen(vm) { settings = false }
            }
        }
    }
}
